# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Environment-local application resolution. Service zones belong to the environment network
# state and attach to exactly one VPC; shared Google API zones remain in the shared DNS hub.

locals {
  root           = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars       = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  environment    = local.env_vars.locals.environment
  inventory      = jsondecode(file("${get_repo_root()}/contracts/dns-domain-inventory.json"))
  hostnames      = local.inventory.environment_naming.hostnames[local.environment]
  module_version = "v0.4.0"
}

terraform {
  source = "${local.root.locals.module_source_base}//dns?ref=${local.module_version}"
}
