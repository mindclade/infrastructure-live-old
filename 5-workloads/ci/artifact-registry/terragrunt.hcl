# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "common_projects" {
  config_path = "../../../1-org/common-projects"
  mock_outputs = {
    project_ids     = { ci = "mc-common-ci" }
    project_numbers = { ci = "000000000001" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../1-org/kms"
  mock_outputs = {
    crypto_key_ids = {
      ci_artifacts = "projects/mock/locations/us-central1/keyRings/mock-global/cryptoKeys/ci-artifacts"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  module_version = "v0.4.0"
}

terraform {
  source = "${include.root.locals.module_source_base}//artifact_registry?ref=${local.module_version}"
}

inputs = {
  project_id          = dependency.common_projects.outputs.project_ids["ci"]
  project_number      = dependency.common_projects.outputs.project_numbers["ci"]
  location            = include.root.locals.region
  repository_id       = "releases"
  description         = "Reviewed ARC release candidates; all consumers use immutable digests."
  environment         = "ci"
  owner               = "platform"
  data_classification = "internal"
  kms_key_name        = dependency.kms.outputs.crypto_key_ids["ci_artifacts"]

  cleanup_policy_dry_run   = true
  untagged_retention_days  = 30
  minimum_versions_to_keep = 30

  labels = merge(include.root.locals.common_labels, {
    authority = "artifact-release"
  })
}
