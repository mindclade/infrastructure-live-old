# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Admission policy. Default rule requires the environment's governed attestor.
#
# The control that makes everything the build pipeline does actually matter. Signing an image
# and generating an SBOM changes nothing on its own — a cluster that will run any image gains
# nothing from the signature existing. This is where the signature becomes a precondition for
# the pod starting.
#
# Most of the policy is in _envcommon/binauthz.hcl, including the environment-dependent
# enforcement mode: development audits while staging and production block. Exact upstream Argo
# control-plane digest exceptions are loaded from the repository contract; namespace-wide and
# registry-prefix bypasses are prohibited.

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
    cluster_name = "mc-development"
    location     = "europe-west4"
    project_id   = "mc-development-platform"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "shared" {
  config_path = "../../../2-environments/development/shared-projects"
  mock_outputs = {
    project_ids     = { platform = "mc-development-platform" }
    project_numbers = { platform = "100000000001" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "automation" {
  config_path = "../../../1-org/automation-iam"
  mock_outputs = { supply_chain_service_accounts = {
    signer = "sa-artifact-signer@mc-common-ci.iam.gserviceaccount.com"
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

inputs = {
  project_id     = dependency.gke.outputs.project_id
  project_number = dependency.shared.outputs.project_numbers["platform"]
  cluster        = "${dependency.gke.outputs.location}.${dependency.gke.outputs.cluster_name}"

  attestor_key_ring = dependency.kms.outputs.key_ring_name

  # ---------------------------------------------------------------------------------------
  # Attestation authority
  # ---------------------------------------------------------------------------------------
  # One issuer per evidence stage. Production admission trusts only deployment-attestor, so
  # builder or qualifier compromise alone cannot deploy. Nothing in this cluster can sign.
  attestor_signers = {
    build-attestor         = []
    qualification-attestor = []
    deployment-attestor    = ["serviceAccount:${dependency.automation.outputs.supply_chain_service_accounts["signer"]}"]

    # Human signers only, and named in github-config's teams catalogue as @biosecurity. A
    # service account here would make the review automatable, which defeats the reason the
    # attestor exists.
    biosecurity-review-attestor = []
  }

  labels = include.root.locals.common_labels
}
