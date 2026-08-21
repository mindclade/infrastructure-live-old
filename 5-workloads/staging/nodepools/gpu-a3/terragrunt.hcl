# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# A3 GPU node pool. Tainted; scheduled through Kueue.
#
# A3 High: 8× H100 80GB per node. The workhorse pool — most training and every evaluation
# sweep runs here, and ../gpu-a4 is reserved for the runs that genuinely need more.
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
    cluster_name = "mc-staging"
    location     = "us-central1"
    project_id   = "mc-staging-platform"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  name       = "gpu-a3"
  cluster    = dependency.gke.outputs.cluster_name
  project_id = dependency.gke.outputs.project_id

  machine_type      = "a3-highgpu-8g"
  accelerator_type  = "nvidia-h100-80gb"
  accelerator_count = 8

  # Four nodes, 32 H100s, in staging. The ceiling exists to bound a mistake rather than
  # to express demand: a sweep that requests more than this queues instead of provisioning
  # it, and a queued job is a conversation while a provisioned one is an invoice.
  max_node_count = 4

  # A3 needs a specific zone with capacity, not a region.
  #
  # A regional pool spreads across every zone in the region and provisioning fails in
  # whichever zone has no H100 stock — which presents as a node pool that is "creating" for
  # forty minutes and then errors. Pinning the zone makes a capacity problem visible
  # immediately and makes a reservation possible.
  node_locations = [include.root.locals.account_vars.locals.gpu_zone]

  # GPUDirect-TCPX needs the multi-NIC layout the A3 shape provides. Without it, multi-node
  # training falls back to the standard network path and the all-reduce becomes the
  # bottleneck — the run completes, several times slower, with nothing in the logs to say
  # why.
  enable_gpudirect                = true
  additional_node_network_configs = 4

  # Local SSD as the scratch tier. Checkpoints go to GCS (../../storage/gcs-checkpoints);
  # this is for the dataset shards and the compiled kernels, both of which are rebuildable
  # and neither of which should be crossing the network on every step.
  local_ssd_count       = 16
  ephemeral_storage_ssd = true

  # Compact placement. Inter-node latency dominates a distributed all-reduce, and a pool
  # spread across a zone's failure domains can be several times slower than one placed
  # together — for the same hardware and the same bill.
  placement_policy = {
    type = "COMPACT"
  }

  # Kueue admits work onto this pool. The taint from envcommon keeps anything without a
  # toleration off it; these labels are what a Kueue ResourceFlavor selects on.
  node_labels = {
    "mindclade.dev/accelerator"                       = "h100"
    "mindclade.dev/pool"                              = "gpu-a3"
    "cloud.google.com/gke-max-shared-clients-per-gpu" = "1"
  }
}
