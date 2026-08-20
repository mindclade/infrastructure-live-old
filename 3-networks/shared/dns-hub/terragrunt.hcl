# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

locals { module_version = "v0.1.0" }
terraform {
  source = "${include.root.locals.module_source_base}//dns?ref=${local.module_version}"
}

dependency "common_projects" {
  config_path = "../../../1-org/common-projects"
  mock_outputs = { project_ids = { dns = "mc-common-dns" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "development_vpc" {
  config_path = "../../development/shared-vpc-host"
  mock_outputs = { network_self_links = { development = "projects/mock/global/networks/development" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}
dependency "staging_vpc" {
  config_path = "../../staging/shared-vpc-host"
  mock_outputs = { network_self_links = { staging = "projects/mock/global/networks/staging" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}
dependency "production_vpc" {
  config_path = "../../production/shared-vpc-host"
  mock_outputs = { network_self_links = { production = "projects/mock/global/networks/production" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id = dependency.common_projects.outputs.project_ids["dns"]
  zones = {
    gcp-internal = {
      domain     = "gcp.mindclade.com."
      visibility = "private"
      networks = [
        dependency.development_vpc.outputs.network_self_links["development"],
        dependency.staging_vpc.outputs.network_self_links["staging"],
        dependency.production_vpc.outputs.network_self_links["production"],
      ]
      records = {}
    }
  }
  labels = merge(include.root.locals.common_labels, { scope = "private" })
}
