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
  module_version = "v0.1.1"

  # A local as well as an input, so a pool that needs an ADDITIONAL taint can concat onto it
  # rather than retyping it — see nodepools/gpu-a4. Redeclaring the accelerator taint by hand
  # in a unit is how one pool ends up with a subtly different effect from the others.
  gpu_taints = [
    {
      key    = "nvidia.com/gpu"
      value  = "present"
      effect = "NO_SCHEDULE"
    },
  ]
}

terraform {
  source = "${local.root.locals.module_source_base}//gpu_node_pool?ref=${local.module_version}"
}

inputs = {
  cluster  = "${local.account_vars.locals.prefix}-${local.environment}"
  location = local.account_vars.locals.region

  # Zero minimum, always. A GPU pool with min_count > 1 is a standing charge for capacity
  # nobody asked for; Kueue scales it up when a job is admitted.
  min_node_count = 0

  autoscaling = true

  # Taint so that only workloads that explicitly tolerate a GPU node land on one. Without
  # it, an ordinary deployment with no resource limits schedules onto an A4 and holds it.
  taints = local.gpu_taints

  # Repair yes, upgrade no. An automatic upgrade that drains a node mid-training loses the
  # run — checkpointing helps but does not make it free.
  auto_repair  = true
  auto_upgrade = false

  # Spot in non-production only. A preemption during a production inference request is a
  # customer-visible error; during a development experiment it is a retry.
  spot = local.environment != "production"

  enable_gvnic       = true
  enable_fast_socket = true
  # Keep production on GKE's default qualified driver branch; lower environments exercise
  # the newest driver first.
  gpu_driver_version    = local.environment == "production" ? "DEFAULT" : "LATEST"
  ephemeral_storage_ssd = true

  enable_secure_boot          = true
  enable_integrity_monitoring = true

  # Workload Identity on the pool. Without it, pods fall back to the node service account,
  # which is a shared identity across everything scheduled there.
  workload_metadata_mode = "GKE_METADATA"

  labels = merge(local.root.locals.common_labels, {
    accelerator = "gpu"
    cost-centre = "research"
  })
}
