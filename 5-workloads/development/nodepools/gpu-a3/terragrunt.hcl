# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# H100 A3 Mega accelerator pool. Tainted, scales to zero, and scheduled through Kueue.
#
# THE COST NOTE, because it is the thing that actually goes wrong: one node of this shape
# left running costs roughly what the rest of this environment costs in a month, and nothing
# breaks to tell you. min_node_count is 0 in _envcommon/gpu-nodepool.hcl and must stay there.
# If a job is queued and no node exists, that is Kueue working.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/gpu-nodepool.hcl"
  expose         = true
  merge_strategy = "deep"
}

dependency "gke" {
  config_path = "../../gke"

  mock_outputs = {
    cluster_name     = "mc-development"
    cluster_location = "us-central1"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "shared" {
  config_path                             = "../../../../2-environments/development/shared-projects"
  mock_outputs                            = { project_ids = { platform = "mc-development-platform" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "vpc" {
  config_path                             = "../../../../3-networks/development/shared-vpc-host"
  mock_outputs                            = { pods_range_names = { development = "mock-development-pods" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "node_identities" {
  config_path = "../../node-identities"
  mock_outputs = {
    service_accounts = { gpu_nodes = { email = "sa-gpu-nodes@mc-development-platform.iam.gserviceaccount.com" } }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  name                       = "gpu-h100"
  profile                    = "gke-h100-a3-megagpu-8g"
  zone                       = include.root.locals.account_vars.locals.gpu_zone
  cluster_name               = dependency.gke.outputs.cluster_name
  project_id                 = dependency.shared.outputs.project_ids["platform"]
  node_service_account_email = dependency.node_identities.outputs.service_accounts["gpu_nodes"].email
  pod_secondary_range_name   = dependency.vpc.outputs.pods_range_names[include.envcommon.locals.environment]
  capacity_mode              = "ON_DEMAND"
  total_max_nodes            = 4
}
