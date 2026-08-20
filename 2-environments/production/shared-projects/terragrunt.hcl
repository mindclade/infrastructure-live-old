# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Per-environment shared projects and budgets. See _envcommon/shared-projects.hcl.

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
    folder_ids = { production = "folders/000000000000" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  folder_id = dependency.folders.outputs.folder_ids["production"]
  # The bulk of the organization budget in bootstrap. Production overspending is a business
  # event that someone should be told about, not a mistake to be caught — which is why the
  # threshold rules in bootstrap include a forecast alert rather than only current spend.
  budget_amount = 30000
}
