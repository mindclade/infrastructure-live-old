# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

locals { module_version = "v0.1.0" }
terraform {
  source = "${include.root.locals.module_source_base}//dns?ref=${local.module_version}"
}

dependency "common_projects" {
  config_path                             = "../../../../1-org/common-projects"
  mock_outputs                            = { project_ids = { dns = "mc-common-dns" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id = dependency.common_projects.outputs.project_ids["dns"]
  zones = {
    mindclade_com = {
      domain              = "mindclade.com."
      visibility          = "public"
      dnssec              = true
      deletion_protection = true
      records = {

      }
    }
  }
  labels = merge(include.root.locals.common_labels, {
    scope  = "public"
    domain = "mindclade-com"
  })
}
