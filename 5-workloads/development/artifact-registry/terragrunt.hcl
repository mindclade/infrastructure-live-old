# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/artifact-registry.hcl"
  merge_strategy = "deep"
}

dependency "shared" {
  config_path = "../../../2-environments/development/shared-projects"
  mock_outputs = {
    project_ids     = { platform = "mc-development-platform" }
    project_numbers = { platform = "100000000001" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../2-environments/development/kms"
  mock_outputs = {
    crypto_key_ids = { storage = "projects/mock/locations/us-central1/keyRings/mock-development/cryptoKeys/storage" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id     = dependency.shared.outputs.project_ids["platform"]
  project_number = dependency.shared.outputs.project_numbers["platform"]
  kms_key_name   = dependency.kms.outputs.crypto_key_ids["storage"]
}
