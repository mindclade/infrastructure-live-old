# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Independent U.S. recovery repository. Promotion remains digest-only and inactive until a
# connected replication/restore qualification supplies immutable evidence.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//artifact_registry?ref=${local.module_version}"
}

locals {
  module_version = "v0.4.0"
  environment    = "development"
}

dependency "shared" {
  config_path = "../../../2-environments/development/shared-projects"
  mock_outputs = {
    project_ids     = { platform = "mc-development-platform" }
    project_numbers = { platform = "100000000001" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms_dr" {
  config_path = "../../../2-environments/development/kms-dr"
  mock_outputs = {
    crypto_key_ids = { artifacts = "projects/mock/locations/us-east4/keyRings/mock-development-dr/cryptoKeys/artifacts" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id               = dependency.shared.outputs.project_ids["platform"]
  project_number           = dependency.shared.outputs.project_numbers["platform"]
  location                 = include.root.locals.dr_region
  repository_id            = "releases"
  description              = "U.S. recovery copy of qualified immutable workload images."
  environment              = local.environment
  owner                    = "platform"
  data_classification      = "internal"
  kms_key_name             = dependency.kms_dr.outputs.crypto_key_ids["artifacts"]
  cleanup_policy_dry_run   = true
  untagged_retention_days  = 30
  minimum_versions_to_keep = 30
  labels = merge(include.root.locals.common_labels, {
    authority = "artifact-release-dr"
  })
}
