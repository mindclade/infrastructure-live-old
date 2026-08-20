# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# General-purpose CPU node pool.
#
# Where everything that is not a training job runs: the control-plane services, the
# reconcilers, ArgoCD itself, and the ingestion workers. Sized to be boring — the interesting
# capacity decisions are all in ../gpu-a3 and ../gpu-a4.
#
# It uses the dedicated CPU module. GPU and CPU capacity are separate authorities because
# their lifecycle, interruption, topology, and identity contracts are not interchangeable.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/cpu-nodepool.hcl"
  expose         = true
  merge_strategy = "deep"
}

dependency "gke" {
  config_path = "../../gke"

  mock_outputs = {
    cluster_name     = "mc-staging"
    cluster_location = "us-central1"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "shared" {
  config_path = "../../../../2-environments/staging/shared-projects"
  mock_outputs = {
    project_ids = { platform = "mc-staging-platform" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "vpc" {
  config_path = "../../../../3-networks/staging/shared-vpc-host"
  mock_outputs = {
    pods_range_names = { staging = "mock-staging-pods" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  cluster_name             = dependency.gke.outputs.cluster_name
  project_id               = dependency.shared.outputs.project_ids["platform"]
  pod_secondary_range_name = dependency.vpc.outputs.pods_range_names[include.envcommon.locals.environment]
}
