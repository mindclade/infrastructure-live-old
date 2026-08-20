# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# Lakehouse buckets.
#
# The medallion layout — raw, curated, features — as three buckets rather than three prefixes
# in one. Prefixes would be simpler; separate buckets are what make the boundary enforceable,
# because IAM, CMEK, retention, and lifecycle are all bucket-scoped in GCS. A prefix-based
# lakehouse has one access decision for all three tiers.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/gcs-bucket.hcl"
  expose         = true
  merge_strategy = "deep"
}

dependency "data" {
  config_path = "../../../../4-projects/production/data"

  mock_outputs = {
    project_id = "mc-production-data"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  env = include.envcommon.locals.environment
}

inputs = {
  project_id = dependency.data.outputs.project_id

  buckets = {
    # Immutable landing zone. Everything downstream is derived from here, so a bad
    # transformation is recoverable by re-deriving — but only if this tier was never
    # overwritten.
    raw = {
      name       = "${include.root.locals.prefix}-${local.env}-lake-raw"
      versioning = true

      # Retention lock, not just versioning. The reason is reproducibility: a model trained
      # on a dataset must be re-derivable from the raw tier years later, and a lifecycle rule
      # that deleted the inputs makes the training run unauditable.
      retention_days = 2555

      lifecycle_rules = [
        { condition = { age = 30 }, action = { type = "SetStorageClass", storage_class = "NEARLINE" } },
        { condition = { age = 365 }, action = { type = "SetStorageClass", storage_class = "COLDLINE" } },
      ]
    }

    # Cleaned and conformed. Rebuildable from raw, so it is the cheapest tier to lose and
    # gets no retention lock.
    curated = {
      name                   = "${include.root.locals.prefix}-${local.env}-lake-curated"
      versioning             = true
      hierarchical_namespace = true

      lifecycle_rules = [
        { condition = { age = 90 }, action = { type = "SetStorageClass", storage_class = "NEARLINE" } },
        { condition = { num_newer_versions = 2, with_state = "ARCHIVED" }, action = { type = "Delete" } },
      ]
    }

    # Training features. Read at high throughput by every job, so it stays at STANDARD for
    # its whole life — a Nearline retrieval charge on every epoch would exceed the storage
    # saving several times over.
    features = {
      name                   = "${include.root.locals.prefix}-${local.env}-lake-features"
      versioning             = false
      hierarchical_namespace = true

      # No class transitions, deliberately. See above.
      lifecycle_rules = [
        # Production feature sets expire; they are regenerated from curated in minutes.
        { condition = { age = 60 }, action = { type = "Delete" } },
      ]
    }
  }

  labels = merge(include.root.locals.common_labels, {
    data-class  = "lakehouse"
    cost-centre = "data"
  })
}
