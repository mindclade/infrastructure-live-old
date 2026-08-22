# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Backup for GKE, cross-region destination, bucket replication.
#
# What this protects against is not a region failing — the clusters are regional and the
# state buckets are dual-region already. It protects against DELETION: a bad apply, a
# compromised credential, a namespace removed by an ArgoCD prune that should not have run.
# Both halves of a dual-region bucket agree an object is gone.
#
# So every destination here is in a different region, written by an identity that cannot
# write to the source, and configured never to propagate a delete.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//backup_dr?ref=${local.module_version}"
}

locals {
  module_version = "v0.4.0"
  env_vars       = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env            = local.env_vars.locals.environment

  # The independent U.S. recovery region. The recovery source stays inside the residency
  # boundary while avoiding the primary region's failure domain.
  replica_region = include.root.locals.dr_region
}

dependency "gke" {
  config_path = "../gke"

  mock_outputs = {
    cluster_name = "mc-production"
    location     = "us-central1"
    project_id   = "mc-production-platform"
    cluster_id   = "projects/mc-production-platform/locations/us-central1/clusters/mc-production"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms_dr" {
  config_path = "../../../2-environments/production/kms-dr"

  mock_outputs = {
    crypto_key_ids = {
      storage = "projects/mock/locations/us-east4/keyRings/mock-production-dr/cryptoKeys/storage"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id = dependency.gke.outputs.project_id

  # ---------------------------------------------------------------------------------------
  # GKE Backup
  # ---------------------------------------------------------------------------------------
  # Backs up the cluster's OBJECTS and its persistent volumes. Not the manifests — those are
  # in the gitops repo and are recoverable by re-syncing.
  #
  # What is NOT recoverable from git is the state a workload accumulated: a PVC holding a
  # partially-written dataset, a StatefulSet's identity, a Job's completion record. That is
  # what this holds.
  gke_backup = {
    plan_name = "${include.root.locals.prefix}-${local.env}-backup"
    cluster   = dependency.gke.outputs.cluster_id

    # The backup lives in the replica region, not beside the cluster.
    location = local.replica_region

    # Hourly production recovery points bound accumulated cluster-state loss.
    cron_schedule = "0 * * * *"

    # Everything except the namespaces whose contents are entirely derived. Backing up
    # gatekeeper-system restores a Gatekeeper whose constraints came from git anyway, and
    # restoring a stale copy of them is worse than restoring none.
    all_namespaces = true
    excluded_namespaces = [
      "gatekeeper-system",
      "kube-system",
      "gmp-system",
    ]

    # Volume data, not just object definitions. Without this the restore recreates empty
    # PVCs, which looks like success and is not.
    include_volume_data = true
    include_secrets     = true

    encryption_key = dependency.kms_dr.outputs.crypto_key_ids["storage"]

    retention = {
      # 30 days of daily backups in production. The number that matters is not the count but
      # whether it exceeds the time it takes anyone to NOTICE a deletion — which for a
      # rarely-used namespace is measured in weeks, not hours.
      backup_retain_days = 30

      # Delete-lock on the plan itself, so a compromised credential cannot shorten the
      # retention and then delete.
      backup_delete_lock_days = 7
    }
  }

  # ---------------------------------------------------------------------------------------
  # Bucket replication
  # ---------------------------------------------------------------------------------------
  # The data buckets, replicated to the independent U.S. recovery region on a schedule. Same shape as the
  # state replication in bootstrap/modules/state/replication.tf, and for the same reason.
  bucket_replication = {
    for name in ["checkpoints", "lake-raw"] : name => {
      source_bucket      = "${include.root.locals.prefix}-${local.env}-${name}"
      destination_bucket = "${include.root.locals.prefix}-${local.env}-${name}-replica"
      destination_region = local.replica_region
      kms_key_name       = dependency.kms_dr.outputs.crypto_key_ids["storage"]

      # NEVER propagate a delete. Deletion is precisely the event this defends against —
      # replicating it would make the replica agree the object is gone, which is an expensive
      # way to have no backup.
      delete_objects_unique_in_sink              = false
      delete_objects_from_source_after_transfer  = false
      overwrite_objects_already_existing_in_sink = true

      schedule = "0 * * * *"

      # Longer retention on the replica than the source, again matching bootstrap: the
      # replica exists for the case where the primary was tampered with, and that is
      # typically noticed weeks later.
      retention_days = 90
    }
  }

  # `lake-features` is deliberately absent from the list above. It is regenerated from
  # `lake-curated` in minutes, and replicating it doubles the storage cost of the largest
  # rebuildable dataset in the estate for no recovery benefit.

  labels = merge(include.root.locals.common_labels, {
    purpose = "backup"
  })
}
