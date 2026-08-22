# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Cloud KMS key ring reserved for Binary Authorization attestor signing keys.
#
# This unit owns the ring only. The keys in it are created by the dependent `binauthz`
# units, not here, because each attestor key is bound to the attestor it signs for.
# Declaring those keys here would split their authority across two state files.
#
# Org-scoped rather than per-environment: an attestation travels with an image digest across
# environments, so the key that signed it cannot belong to one of them. This is the same
# reason the ring survived the split of the former single `1-org/kms` unit into per-environment
# units — see docs/module-interface-contract.md.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//kms?ref=${local.module_version}"
}

locals {
  module_version = "v0.4.0"
}

inputs = {
  project_id = include.root.locals.seed_project_id
  location   = include.root.locals.region

  key_ring_name = "${include.root.locals.prefix}-binauthz"

  # This state owns only the protected ring. The dependent Binary Authorization states
  # create their attestor keys in it and must remain the sole CryptoKey owners.
  ring_only = true

  # The module rejects ring_only when either map is nonempty.
  keys         = {}
  signing_keys = {}

  labels = include.root.locals.common_labels
}
