# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# A4 GPU node pool. Tainted; scheduled through Kueue.
#
# A4: 8× B200 per node. The largest shape in the estate, and the one where every number in
# ../gpu-a3's cost note roughly doubles.
#
# It exists as a separate pool rather than a larger max on the A3 pool because the two are
# not substitutable: a run compiled and tuned for H100 does not simply go faster on B200, and
# Kueue needs to be able to admit to one and not the other. A single pool with mixed shapes
# would let a job land on whichever node happened to be free.
#
# In staging this pool is for compatibility and throughput testing before a run is
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
    cluster_name = "mc-staging"
    location     = "europe-west4"
    project_id   = "mc-staging-platform"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  name       = "gpu-a4"
  cluster    = dependency.gke.outputs.cluster_name
  project_id = dependency.gke.outputs.project_id

  machine_type      = "a4-highgpu-8g"
  accelerator_type  = "nvidia-b200"
  accelerator_count = 8

  # Two nodes. Enough to prove a multi-node all-reduce works on this shape, which is the
  # whole reason the pool exists in staging.
  max_node_count = 2

  node_locations = ["europe-west4-b"]

  # SPOT IS OFF, against the envcommon default of "spot in non-production".
  #
  # The default is right for A3, where a preemption costs a retry. It is wrong here: B200
  # capacity is scarce enough that a preempted A4 node is frequently not replaceable for
  # hours, so a spot A4 pool spends most of its life at zero nodes while jobs queue against
  # capacity that is nominally available. Paying on-demand for two nodes that actually exist
  # is cheaper than an engineer waiting for capacity that does not.
  spot = false

  enable_gpudirect = true
  # A4 exposes more NICs than A3. Under-declaring here does not error — it silently gives
  # the RDMA path less bandwidth than the hardware has.
  additional_node_network_configs = 8

  local_ssd_count       = 32
  ephemeral_storage_ssd = true

  placement_policy = {
    type = "COMPACT"
  }

  node_labels = {
    "mindclade.dev/accelerator"                       = "b200"
    "mindclade.dev/pool"                              = "gpu-a4"
    "cloud.google.com/gke-max-shared-clients-per-gpu" = "1"
  }

  # A second taint on top of the accelerator taint from envcommon. Tolerating "there is a
  # GPU here" is not sufficient to land on this pool — a workload has to name it, which
  # means an A3 job cannot drift onto B200 capacity because the A3 pool was busy.
  taints = concat(
    include.envcommon.locals.gpu_taints,
    [
      {
        key    = "mindclade.dev/pool"
        value  = "gpu-a4"
        effect = "NO_SCHEDULE"
      },
    ],
  )
}
