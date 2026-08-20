# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/node-identities.hcl"
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

inputs = {
  project_id     = dependency.shared.outputs.project_ids["platform"]
  project_number = dependency.shared.outputs.project_numbers["platform"]
}
