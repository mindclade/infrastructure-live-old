# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Reliable, non-accelerator workload capacity. The GKE module owns a separate redundant
# system pool; this pool is for application and CPU batch workloads.

locals {
  root         = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  environment    = local.env_vars.locals.environment
  module_version = "4d5c0105295bf4a01b770fb75f6a8db5c22c8f79"
}

terraform {
  source = "${local.root.locals.module_source_base}//cpu_node_pool?ref=${local.module_version}"
}

inputs = {
  name               = "cpu-general"
  region             = local.account_vars.locals.region
  node_locations     = [for suffix in ["a", "b", "c"] : "${local.account_vars.locals.region}-${suffix}"]
  service_account_id = "sa-cpu-nodes"
  profile            = "GENERAL_PURPOSE"
  capacity_type      = "ON_DEMAND"
  spot_approval      = null

  environment         = local.environment
  owner               = "platform"
  data_classification = "confidential"

  total_min_nodes   = local.environment == "production" ? 3 : (local.environment == "staging" ? 1 : 0)
  total_max_nodes   = local.environment == "production" ? 50 : (local.environment == "staging" ? 20 : 10)
  max_pods_per_node = 64

  boot_disk_type    = "pd-balanced"
  boot_disk_size_gb = 100
  pod_pids_limit    = 4096

  upgrade_max_surge       = 1
  upgrade_max_unavailable = 0
  node_drain_grace_period = "900s"
  node_drain_pdb_timeout  = "600s"

  resource_labels = merge(local.root.locals.common_labels, {
    authority   = "terraform"
    cost_centre = "platform"
  })
  node_labels = {
    "mindclade.dev/workload-class" = "cpu"
  }
}
