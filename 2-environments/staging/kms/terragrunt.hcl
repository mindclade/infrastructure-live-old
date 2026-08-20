# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# Cloud KMS key ring for staging — rotation schedules, HSM protection.
#
# Split out of the former single `1-org/kms` unit, which held all three environments plus the
# global ring in ONE state file. That meant a development change and a production change were
# the same plan and the same lock. See docs/module-interface-contract.md.
#
# THE RING NAME IS A CONTRACT. `_envcommon/gcs-bucket.hcl` builds its `encryption_key` by
# string interpolation rather than through a dependency block:
#
#   projects/<seed>/locations/<region>/keyRings/<prefix>-staging/cryptoKeys/storage
#
# so a ring renamed here does not fail the plan — it produces buckets pointing at a key that
# does not exist, and the failure arrives at apply time naming only a 404. Renaming a ring
# means editing that file in the same change.
#
# Key rings cannot be deleted, and ring names cannot be reused for a different purpose.
# Adding one is cheap; getting the layout wrong is permanent.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//kms?ref=${local.module_version}"
}

locals {
  module_version = "v0.1.1"
}

inputs = {
  project_id = include.root.locals.seed_project_id
  location   = include.root.locals.region

  # Environment-scoped rings are what make "revoke development's access to production data" a
  # single IAM change rather than an audit of every bucket.
  key_ring_name = "${include.root.locals.prefix}-staging"

  # Symmetric CMEK for this environment. `destroy_scheduled_duration_seconds` is left at the
  # module default (30 days), which is the longest window GCP allows between "destroy
  # requested" and "destroyed". Destroying a key makes everything encrypted under it
  # permanently unreadable — no support ticket recovers it, and the backup is encrypted with
  # the same key.
  #
  # 90-day rotation. Rotation does not re-encrypt existing data — it changes which version new
  # writes use — so a short period costs nothing and bounds how much data any one key version
  # protects.
  keys = {
    # Application-layer secrets encryption for the GKE control plane.
    gke = {
      rotation_period_seconds = 7776000
      protection_level        = "HSM"
    }

    # GCS CMEK. The name `storage` is the one _envcommon/gcs-bucket.hcl interpolates.
    storage = {
      rotation_period_seconds = 7776000
      protection_level        = "HSM"
    }

    # Secret Manager replicas in 5-workloads/<env>/secret-manager.
    secrets = {
      rotation_period_seconds = 7776000
      protection_level        = "HSM"
    }

    # Cloud SQL CMEK for the browser plane's datastore — canvas documents, the run log, and
    # handoff handles.
    sql = {
      rotation_period_seconds = 7776000
      protection_level        = "HSM"
    }
  }

  # ------------------------------------------------------------------------------------
  # The BFF's downstream token-signing key
  # ------------------------------------------------------------------------------------
  # THE HIGHEST-BLAST-RADIUS CREDENTIAL IN THE ESTATE. Every other secret here is bounded by
  # something else: the session key is inert without a matching IAP assertion, the DNS
  # credential is scoped to three public zones, the Athens deploy key is read-only.
  #
  # A leaked token-signing key is bounded by NOTHING — it mints tokens for any principal
  # against any audience, to serving, training, and the registry alike. So it is the one key
  # that must not exist outside KMS in the first place: ASYMMETRIC_SIGN means the private half
  # never leaves, signing is an API call, and a compromised pod has nothing to exfiltrate.
  #
  # It lives in `signing_keys` rather than `keys` because Cloud KMS rejects a rotation period
  # on an asymmetric key. Rotation is a deliberate sequence — add a version, publish the
  # public key, wait for verifiers, disable the old version.
  signing_keys = {
    bff-downstream-jwt = {
      algorithm        = "RSA_SIGN_PKCS1_2048_SHA256"
      protection_level = "HSM"
    }
  }

  labels = include.root.locals.common_labels
}
