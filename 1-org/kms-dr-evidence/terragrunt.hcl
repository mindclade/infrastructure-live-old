# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "common_projects" {
  config_path = "../common-projects"
  mock_outputs = {
    project_ids     = { security = "mc-common-security" }
    project_numbers = { security = "000000000001" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  module_version = "v0.4.0"
}

terraform {
  source = "${include.root.locals.module_source_base}//kms?ref=${local.module_version}"
}

inputs = {
  project_id    = dependency.common_projects.outputs.project_ids["security"]
  location      = "us"
  key_ring_name = "${include.root.locals.prefix}-dr-evidence"
  keys = {
    dr-evidence = {
      rotation_period_seconds = 7776000
      protection_level        = "HSM"
    }
  }
  encrypter_decrypters = {
    dr-evidence = [
      "serviceAccount:service-${dependency.common_projects.outputs.project_numbers["security"]}@gs-project-accounts.iam.gserviceaccount.com",
    ]
  }
  labels = merge(include.root.locals.common_labels, {
    "data-classification" = "restricted"
    purpose               = "dr-evidence"
  })
}
