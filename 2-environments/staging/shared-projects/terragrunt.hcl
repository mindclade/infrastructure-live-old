# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Per-environment shared projects and budgets. See _envcommon/shared-projects.hcl.
#
# Staging exists to be a rehearsal for production, so it overrides as little as possible:
# only the budget, which reflects that staging runs at a fraction of production's scale. A
# control that production has and staging does not makes staging stop being a rehearsal.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/shared-projects.hcl"
  expose         = true
  merge_strategy = "deep"
}

dependency "folders" {
  config_path = "../../../1-org/folders"

  mock_outputs = {
    folder_ids = { staging = "folders/000000000000" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  folder_id     = dependency.folders.outputs.folder_ids["staging"]
  budget_amount = 12000
}
