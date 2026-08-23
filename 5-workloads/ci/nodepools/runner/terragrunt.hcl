# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Dedicated capacity for ARC runner pods.
#
# THE DEFECT THIS CLOSES. `../../arc-gke` creates the cluster and its system node pool and
# nothing else, so every runner scale set in `gitops/arc/values/` — which carries a
# `nodeSelector` and no toleration — schedules onto the system pool, beside the ARC controller
# that decides which jobs run. Runner pods execute untrusted pull-request code. A container
# escape or a runner that simply exhausts the node then takes out the controller and every
# other runner with it, and the blast radius is the whole artifact-authority cluster rather
# than one job.
#
# The label and taint below are the half of the contract this repository owns. The paired GitOps
# source selects that label and carries the exact toleration; `validate-arc-runner-placement.py`
# checks both halves. Ordering still matters: apply and qualify this pool before reconciling the
# GitOps placement change. A zero runner minimum is not a safety gate because a queued job can
# scale an active set from zero.
#
# NOT SPOT, deliberately. Spot is the obvious saving on a pool that idles at zero, and it is
# wrong here: a preempted runner does not reschedule its job, it fails it, and a failed
# presubmit is indistinguishable in the GitHub UI from a real test failure. That trade is worth
# revisiting once eviction rates for this machine shape in this region have been measured
# against a real presubmit load — until then `capacity_type` stays ON_DEMAND and
# `spot_approval` stays null, which the module requires as a matched pair.
#
# No `_envcommon/cpu-nodepool.hcl` include. That file reads `env.hcl` without a `try`, and the
# `ci` scope has no `env.hcl` — it is a common-project workload like `../../bazel-remote-cache`,
# not a fourth environment. Including it would fail at parse time before a single input is read.

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
  name                     = "arc-runner"
  region                   = include.root.locals.region
  node_locations           = [for suffix in ["a", "b", "c"] : "${include.root.locals.region}-${suffix}"]
  pod_secondary_range_name = dependency.arc_vpc.outputs.pods_range_names["arc"]

  # A node identity distinct from `sa-arc-system-nodes`, which the controller's pool uses. Same
  # reasoning as the taint: the identity that runs untrusted code must not be the identity that
  # runs the thing deciding what code to run.
  service_account_id = "sa-arc-runner-nodes"
  profile            = "GENERAL_PURPOSE"

  # See the header.
  capacity_type = "ON_DEMAND"
  spot_approval = null

  # Zero floor. Runner scale sets all declare `minRunners: 0`, so between merges this pool costs
  # nothing; the ceiling covers the declared concurrency — build 6 + qualify 4 + canary 1 at a
  # 2 vCPU / 4 GiB request each, which is roughly three runners to an n2-standard-8 once the GKE
  # daemonsets have taken their share.
  total_min_nodes   = 0
  total_max_nodes   = 6
  max_pods_per_node = 64

  # Larger than the platform pools' 100 GiB. A runner's checkout, Bazel outputs, and container
  # layers all land on the node's writable layer, and a full boot disk presents as a job failing
  # partway through with a message about the workspace rather than about disk.
  boot_disk_type    = "pd-balanced"
  boot_disk_size_gb = 200
  pod_pids_limit    = 4096

  additional_taints = [{
    key    = "scheduling.mindclade.dev/arc-runner"
    value  = "true"
    effect = "NO_SCHEDULE"
  }]

  # Surge upgrades with nothing allowed to go unavailable, and the same drain window the
  # platform pools use. A node drained mid-job fails that job rather than rescheduling it, so a
  # longer window for long presubmits is worth having — but it is a reviewed change once GKE's
  # own ceiling on grace_termination_duration is confirmed against a real upgrade, not a number
  # invented here.
  upgrade_max_surge       = 1
  upgrade_max_unavailable = 0
  node_drain_grace_period = "900s"
  node_drain_pdb_timeout  = "600s"

  environment         = "ci"
  owner               = "platform"
  data_classification = "internal"

  resource_labels = merge(include.root.locals.common_labels, {
    authority = "artifact-release"
    isolation = "dedicated-nodepool"
  })
  node_labels = {
    "mindclade.dev/workload-class" = "arc-runner"
  }
}
