# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Admission policy. Default rule DENY, per-namespace allowlist.
#
# The control that makes everything the build pipeline does actually matter. Signing an image
# and generating an SBOM changes nothing on its own — a cluster that will run any image gains
# nothing from the signature existing. This is where the signature becomes a precondition for
# the pod starting.
#
# Most of the policy is in _envcommon/binauthz.hcl, including the environment-dependent
# enforcement mode: production BLOCKS, everything else runs DRYRUN and logs what it would
# have blocked. What is here is the per-namespace exceptions, which are environment-specific
# by nature.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/binauthz.hcl"
  expose         = true
  merge_strategy = "deep"
}

dependency "gke" {
  config_path = "../gke"

  mock_outputs = {
    cluster_name = "mc-staging"
    location     = "europe-west4"
    project_id   = "mc-staging-platform"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "automation" {
  config_path = "../../../1-org/automation-iam"
  mock_outputs = { supply_chain_service_accounts = {
    builder   = "sa-artifact-builder@mc-common-ci.iam.gserviceaccount.com"
    qualifier = "sa-artifact-qualifier@mc-common-ci.iam.gserviceaccount.com"
    signer    = "sa-artifact-signer@mc-common-ci.iam.gserviceaccount.com"
  } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../1-org/kms-binauthz"

  # The attestor signing keys are created by this module in the ring 1-org/kms reserves for
  # them — they are asymmetric SIGN keys bound to a specific attestor, which is why they are
  # not declared alongside the symmetric keys there.
  mock_outputs = {
    key_ring_name = "projects/mock/locations/europe-west4/keyRings/mock-binauthz"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  env = include.envcommon.locals.environment
}

inputs = {
  project_id = dependency.gke.outputs.project_id
  cluster    = "${dependency.gke.outputs.location}.${dependency.gke.outputs.cluster_name}"

  attestor_key_ring = dependency.kms.outputs.key_ring_name

  # ---------------------------------------------------------------------------------------
  # Per-namespace exceptions
  # ---------------------------------------------------------------------------------------
  # Every entry is a decision somebody made rather than a gap somebody left, and each one
  # says what it is for. The default rule from envcommon is REQUIRE_ATTESTATION; these
  # namespaces are the ones where that is either impossible or actively wrong.
  cluster_admission_rules = {
    # Gatekeeper and the managed add-ons. Google publishes these images and does not sign
    # them with our attestors — requiring one would mean Policy Controller itself cannot
    # start, which takes every other constraint down with it.
    "gatekeeper-system" = {
      evaluation_mode  = "ALWAYS_ALLOW"
      enforcement_mode = "DRYRUN_AUDIT_LOG_ONLY"
    }

    # ArgoCD, for the same reason: upstream images, and the component that would have to be
    # running to deploy a signed replacement.
    "argocd" = {
      evaluation_mode  = "ALWAYS_ALLOW"
      enforcement_mode = "DRYRUN_AUDIT_LOG_ONLY"
    }

  }

  # ---------------------------------------------------------------------------------------
  # Attestation authority
  # ---------------------------------------------------------------------------------------
  # One issuer per evidence stage. Production admission trusts only deployment-attestor, so
  # builder or qualifier compromise alone cannot deploy. Nothing in this cluster can sign.
  attestor_signers = {
    build-attestor         = ["serviceAccount:${dependency.automation.outputs.supply_chain_service_accounts["builder"]}"]
    qualification-attestor = ["serviceAccount:${dependency.automation.outputs.supply_chain_service_accounts["qualifier"]}"]
    deployment-attestor    = ["serviceAccount:${dependency.automation.outputs.supply_chain_service_accounts["signer"]}"]

    # Human signers only, and named in github-config's teams catalogue as @biosecurity. A
    # service account here would make the review automatable, which defeats the reason the
    # attestor exists.
    biosecurity-review-attestor = []
  }

  labels = include.root.locals.common_labels
}
