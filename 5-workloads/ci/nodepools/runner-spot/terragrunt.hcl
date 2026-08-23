# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Dormant interruptible capacity for the non-release presubmit lane.
#
# This pool is deliberately unschedulable by every current ARC scale set: it uses a distinct
# workload-class label and carries both the module-managed Spot taint and the presubmit taint below.
# Do not apply it until GitOps defines a separate scale set with both exact tolerations, retry
# semantics distinguish eviction from test failure, quota/cost is approved, and connected eviction
# evidence is retained. Release, signing, canary, build, and qualification lanes stay on the
# on-demand `../runner` pool.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "arc_gke" {
  config_path = "../../arc-gke"

  mock_outputs = {
    cluster_name     = "mc-ci-arc"
    cluster_location = "us-central1"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "common_projects" {
  config_path = "../../../../1-org/common-projects"

  mock_outputs = {
    project_ids = { ci = "mc-common-ci" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "arc_vpc" {
  config_path = "../../../../3-networks/ci/arc-vpc"

  mock_outputs = {
    pods_range_names = { arc = "arc-pods" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  module_version = "v0.4.0"
}

terraform {
  source = "${include.root.locals.module_source_base}//cpu_node_pool?ref=${local.module_version}"
}

inputs = {
  project_id               = dependency.common_projects.outputs.project_ids["ci"]
  cluster_name             = dependency.arc_gke.outputs.cluster_name
  name                     = "arc-presubmit-spot"
  region                   = include.root.locals.region
  node_locations           = [for suffix in ["a", "b", "c"] : "${include.root.locals.region}-${suffix}"]
  pod_secondary_range_name = dependency.arc_vpc.outputs.pods_range_names["arc"]

  service_account_id = "sa-arc-presubmit-spot-nodes"
  profile            = "GENERAL_PURPOSE"

  capacity_type = "SPOT"
  spot_approval = "I ACCEPT EVICTION AND CAPACITY-LOSS RISK"

  # Eight n2-standard-8 nodes bound the proposed 24-runner presubmit lane at approximately three
  # 2-vCPU runners per node after daemonset reservation. The zero floor is mandatory for Spot and
  # is not an activation gate.
  total_min_nodes   = 0
  total_max_nodes   = 8
  max_pods_per_node = 64

  boot_disk_type    = "pd-balanced"
  boot_disk_size_gb = 200
  pod_pids_limit    = 4096

  additional_taints = [{
    key    = "scheduling.mindclade.dev/arc-presubmit"
    value  = "true"
    effect = "NO_SCHEDULE"
  }]

  upgrade_max_surge       = 1
  upgrade_max_unavailable = 0
  node_drain_grace_period = "900s"
  node_drain_pdb_timeout  = "600s"

  environment         = "ci"
  owner               = "platform"
  data_classification = "internal"

  resource_labels = merge(include.root.locals.common_labels, {
    authority = "artifact-presubmit"
    isolation = "interruptible-nodepool"
  })
  node_labels = {
    "mindclade.dev/workload-class" = "arc-presubmit-spot"
  }
}
