# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# B200 A4 High accelerator pool. Tainted, scales to zero, and scheduled through Kueue.
# The legacy gpu-a4 state path is retained deliberately; renaming it would fork Terragrunt state.
#
# It exists as a separate pool rather than a larger max on the H100 pool because the two are
# not substitutable: a run compiled and tuned for H100 does not simply go faster on B200, and
# Kueue needs to be able to admit to one and not the other. A single pool with mixed shapes
# would let a job land on whichever node happened to be free.
#
# In production this pool is for compatibility and throughput testing before a run is
# promoted to a real allocation — not for the run itself.

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
    cluster_name     = "mc-production"
    cluster_location = "us-central1"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "shared" {
  config_path                             = "../../../../2-environments/production/shared-projects"
  mock_outputs                            = { project_ids = { platform = "mc-production-platform" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "vpc" {
  config_path                             = "../../../../3-networks/production/shared-vpc-host"
  mock_outputs                            = { pods_range_names = { production = "mock-production-pods" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "node_identities" {
  config_path = "../../node-identities"
  mock_outputs = {
    service_accounts = { gpu_nodes = { email = "sa-gpu-nodes@mc-production-platform.iam.gserviceaccount.com" } }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  name                       = "gpu-b200"
  profile                    = "gke-b200-a4-highgpu-8g"
  zone                       = include.root.locals.account_vars.locals.gpu_zone
  cluster_name               = dependency.gke.outputs.cluster_name
  project_id                 = dependency.shared.outputs.project_ids["platform"]
  node_service_account_email = dependency.node_identities.outputs.service_accounts["gpu_nodes"].email
  pod_secondary_range_name   = dependency.vpc.outputs.pods_range_names[include.envcommon.locals.environment]
  capacity_mode              = "QUEUED_PROVISIONING"
  enable_compact_placement   = false
  total_max_nodes            = 1
}
