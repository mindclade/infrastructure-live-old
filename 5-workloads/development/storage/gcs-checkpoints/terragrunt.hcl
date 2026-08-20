# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# Training checkpoints. Versioned, lifecycle to coldline.
#
# The bucket a training run writes to every few minutes and reads from exactly once — after
# something has gone wrong. That access pattern is what every setting below is shaped around:
# writes are constant and cheap to serve, reads are rare and urgent.
#
# Checkpoints are also the largest object volume in the estate by a wide margin. A single
# frontier-scale run writes terabytes per day, and the cost of keeping all of it at STANDARD
# for a year exceeds the cost of the GPUs that produced it.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/gcs-bucket.hcl"
  expose         = true
  merge_strategy = "deep"
}

dependency "research" {
  config_path = "../../../../4-projects/development/research"

  mock_outputs = {
    project_id = "mc-development-research"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  env = include.envcommon.locals.environment
}

inputs = {
  project_id = dependency.research.outputs.project_id

  buckets = {
    checkpoints = {
      name = "${include.root.locals.prefix}-${local.env}-checkpoints"

      # A single-region bucket, against the dual-region default used for state.
      #
      # Checkpoints are written from nodes in one zone at multi-gigabyte-per-second
      # aggregate, and dual-region replication of that volume costs more than the checkpoints
      # are worth — they are recreatable by rerunning from the previous one. State is not.
      location = include.root.locals.region

      # Hierarchical namespace. Checkpoint writers rename directories atomically at the end
      # of a step; on a flat bucket that is a copy of every object, which at this size is the
      # difference between a checkpoint taking seconds and taking minutes.
      hierarchical_namespace = true

      versioning = true

      lifecycle_rules = [
        # Aggressive class transitions. A checkpoint older than a week is either the one
        # being resumed from — in which case a Nearline retrieval is negligible against the
        # cost of the run — or it is never read again.
        {
          condition = { age = 7, matches_storage_class = ["STANDARD"] }
          action    = { type = "SetStorageClass", storage_class = "NEARLINE" }
        },
        {
          condition = { age = 30 }
          action    = { type = "SetStorageClass", storage_class = "COLDLINE" }
        },

        # Keep the last three noncurrent versions and no more. Versioning here protects
        # against a truncated write, not against wanting last month's checkpoint back — the
        # run itself is the record of what was trained.
        {
          condition = { num_newer_versions = 3, with_state = "ARCHIVED" }
          action    = { type = "Delete" }
        },

        # Development checkpoints expire. Ninety days is longer than any development run
        # takes and shorter than the point at which nobody remembers what the run was.
        # Production overrides this to keep checkpoints for the life of the model.
        {
          condition = { age = 90 }
          action    = { type = "Delete" }
        },

        # Abandoned multipart uploads. Invisible in the console, billed at full rate, and the
        # usual explanation for a bucket whose listed size does not match its bill.
        {
          condition = { days_since_noncurrent_time = 1, with_state = "ANY" }
          action    = { type = "AbortIncompleteMultipartUpload" }
        },
      ]
    }
  }

  labels = merge(include.root.locals.common_labels, {
    data-class  = "checkpoints"
    cost-centre = "research"
  })
}
