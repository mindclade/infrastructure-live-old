# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# General-purpose CPU node pool.
#
# Where everything that is not a training job runs: the control-plane services, the
# reconcilers, ArgoCD itself, and the ingestion workers. Sized to be boring — the interesting
# capacity decisions are all in ../gpu-a3 and ../gpu-a4.
#
# It shares _envcommon/gpu-nodepool.hcl with those pools because the module is the same and
# most of the hardening is identical. What it overrides is everything accelerator-specific,
# plus the two defaults that only make sense for a GPU pool: a zero minimum and no automatic
# upgrades.

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
    cluster_name    = "mc-staging"
    location        = "europe-west4"
    project_id      = "mc-staging-platform"
    node_subnetwork = "mc-staging-nodes"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  name       = "cpu"
  cluster    = dependency.gke.outputs.cluster_name
  project_id = dependency.gke.outputs.project_id

  machine_type = "n2d-standard-8"

  # NOT zero, unlike the GPU pools. Something has to be running for the cluster to be
  # reachable at all — a pool that scales to zero takes ArgoCD and the metrics agents with
  # it, and the cluster then has no way to schedule the thing that would scale it back up.
  min_node_count = 2
  max_node_count = 20

  # No accelerator, so none of the GPU driver and fast-socket settings from envcommon apply.
  # Explicit nulls rather than omissions: a stale gpu_driver_version inherited onto a CPU
  # pool is accepted by the API and produces nodes that spend two minutes at boot installing
  # a driver for hardware that is not there.
  accelerator_type   = null
  accelerator_count  = 0
  gpu_driver_version = null
  enable_fast_socket = false

  # No taint. This is the pool that takes anything without a toleration, which is what makes
  # the GPU taints in the sibling pools effective — with no untainted pool, an ordinary
  # deployment has nowhere else to go and lands on an A4 anyway.
  taints = []

  # Automatic upgrades ON, against the envcommon default.
  #
  # The reason envcommon disables them is that draining a node mid-training loses the run.
  # Nothing on this pool is a training run: these are replicated services with a
  # PodDisruptionBudget, and they are exactly what should be exercising the upgrade path
  # before a GPU pool ever does.
  auto_upgrade = true
  auto_repair  = true

  # Surge upgrade: one extra node at a time, none unavailable. Slower than a rolling
  # replacement and it never takes capacity below the current requirement, which is what
  # stops an upgrade from becoming an outage on a pool sized close to its minimum.
  upgrade_settings = {
    max_surge       = 1
    max_unavailable = 0
  }

  # Spot on the CPU pool in staging. A preempted reconciler restarts and catches up;
  # envcommon already forbids this in production.
  spot = false

  # Balanced PD rather than the local SSD the GPU pools use. Nothing here has a scratch
  # working set, and local SSD on a spot node is lost on preemption anyway.
  ephemeral_storage_ssd = false
  disk_type             = "pd-balanced"
  disk_size_gb          = 100

  labels = merge(include.root.locals.common_labels, {
    pool        = "cpu"
    cost-centre = "platform"
  })
}
