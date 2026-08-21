# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Shared GPU node-pool defaults.
#
# The expensive one. An A3 or A4 pool left running over a weekend costs more than most
# months of everything else combined, and nothing breaks to tell you — the bill simply
# arrives. Every default here leans toward "scales to zero and stays there".

locals {
  root         = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  environment    = local.env_vars.locals.environment
  module_version = "v0.4.0"
}

terraform {
  source = "${local.root.locals.module_source_base}//gpu_node_pool?ref=${local.module_version}"
}

inputs = {
  region = local.account_vars.locals.region
  zone   = local.account_vars.locals.gpu_zone

  # Zero minimum, always. A GPU pool with min_count > 1 is a standing charge for capacity
  # nobody asked for; Kueue scales it up when a job is admitted.
  total_min_nodes          = 0
  max_pods_per_node        = 16
  boot_disk_size_gb        = 250
  gpu_driver_version       = local.environment == "production" ? "DEFAULT" : "LATEST"
  enable_compact_placement = true
  upgrade_max_surge        = 0
  upgrade_max_unavailable  = 1
  node_drain_grace_period  = "3600s"
  node_drain_pdb_timeout   = "3600s"

  environment         = local.environment
  owner               = "ml-platform"
  data_classification = "confidential"

  resource_labels = merge(local.root.locals.common_labels, {
    authority   = "terraform"
    cost_centre = "research"
  })
}
