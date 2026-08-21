# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "organization_folders" {
  config_path                             = "../../../1-org/folders"
  mock_outputs                            = { folder_ids = { development = "folders/000000000000" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals { module_version = "v0.1.1" }
terraform {
  source = "${include.root.locals.module_source_base}//folder_factory?ref=${local.module_version}"
}

inputs = {
  parent          = dependency.organization_folders.outputs.folder_ids["development"]
  billing_account = include.root.locals.billing_account
  folders = {
    data          = { display_name = "Data", deletion_protection = true }
    research      = { display_name = "Research", deletion_protection = true }
    serving       = { display_name = "Serving", deletion_protection = true }
    security      = { display_name = "Security", deletion_protection = true }
    observability = { display_name = "Observability", deletion_protection = true }
  }
}
