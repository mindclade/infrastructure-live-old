# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "platform" {
  config_path                             = "../../../2-environments/production/shared-projects"
  mock_outputs                            = { project_ids = { platform = "mc-production-platform" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}
dependency "automation" {
  config_path = "../../../1-org/automation-iam"
  mock_outputs = { supply_chain_service_accounts = {
    builder   = "sa-artifact-builder@mc-common-ci.iam.gserviceaccount.com"
    qualifier = "sa-artifact-qualifier@mc-common-ci.iam.gserviceaccount.com"
    signer    = "sa-artifact-signer@mc-common-ci.iam.gserviceaccount.com"
    promoter  = "sa-artifact-promoter@mc-common-ci.iam.gserviceaccount.com"
  } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}
inputs = {
  project_id       = dependency.platform.outputs.project_ids["platform"]
  environment      = "production"
  service_accounts = dependency.automation.outputs.supply_chain_service_accounts
}
