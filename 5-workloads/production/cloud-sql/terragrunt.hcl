# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# The browser plane's datastore: runs, their transcripts and results, canvas documents, and
# handoff handles.
#
# ONE instance for all five tables. Three of them were candidates for separate stores, and
# keeping them together buys one backup posture, one connection pool to reason about, and one
# availability dependency rather than three with three failure modes. The team is small and
# that trade is the right way round.
#
# ---------------------------------------------------------------------------------------
# What this instance is NOT
# ---------------------------------------------------------------------------------------
# It is not a session store. There is no session table and there will not be one: the session
# is a five-minute AEAD cookie bound to the IAP subject, so there is nothing server-side to
# hold. A session store would have made this instance a hard dependency of EVERY browser
# request in the system while only caching a decision.
#
# The handles table shows the contrast, and it is the reason the distinction is worth stating:
# if this instance is unavailable, handoff redemption fails and every other browser request
# keeps working. That difference is what sizes the availability posture here.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//postgres?ref=${local.module_version}"
}

locals {
  module_version = "4d5c0105295bf4a01b770fb75f6a8db5c22c8f79"
  env_vars       = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env            = local.env_vars.locals.environment
}

dependency "shared" {
  config_path = "../../../2-environments/production/shared-projects"

  mock_outputs = {
    project_ids = { platform = "mc-production-platform" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "vpc" {
  config_path = "../../../3-networks/production/shared-vpc-host"

  mock_outputs = {
    network_self_link = {
      production = "projects/mock/global/networks/mock-production-vpc"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

# Private Service Access: the peering range Cloud SQL's private IP comes from. Without it the
# instance can only be created with a public IP, which the org policy forbids outright — so
# the failure is a rejected apply rather than an exposed database.
dependency "psa" {
  config_path = "../../../3-networks/shared/private-service-connect"

  mock_outputs = {
    allocated_ip_ranges = { production = "mc-production-psa" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../2-environments/production/kms"

  mock_outputs = {
    crypto_key_ids = {
      sql = "projects/mock/locations/europe-west4/keyRings/mock-production/cryptoKeys/sql"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id = dependency.shared.outputs.project_ids["platform"]
  name       = "${include.root.locals.prefix}-${local.env}-studio"
  region     = include.root.locals.region

  database_version = "POSTGRES_17"
  edition          = "ENTERPRISE"

  # Production sizing. Production overrides this; the shape of the config does not change.
  tier         = "db-custom-2-7680"
  disk_type    = "PD_SSD"
  disk_size_gb = 50

  # ---------------------------------------------------------------------------------------
  # Network
  # ---------------------------------------------------------------------------------------
  private_network              = dependency.vpc.outputs.network_self_link[local.env]
  allocated_ip_range           = dependency.psa.outputs.allocated_ip_ranges[local.env]
  enable_private_google_access = true

  # Require the Cloud SQL connectors. A raw psql from anywhere in the VPC is otherwise
  # possible, and IAM database authentication below is only meaningful if the connector is the
  # only way in.
  connector_enforcement = "REQUIRED"

  kms_key_name = dependency.kms.outputs.crypto_key_ids["sql"]

  # ---------------------------------------------------------------------------------------
  # Backups and recovery
  # ---------------------------------------------------------------------------------------
  # Canvas documents are the only irreplaceable data in this schema, and their recovery point
  # objective is five minutes. That figure is what point-in-time recovery buys, and it is why
  # transaction log retention is set rather than left at its default.
  #
  # Run events tolerate an hour: a lost transcript is not a lost result, because the result
  # lives in its own table and its artifacts in object storage. Handles tolerate unbounded
  # loss — they are short-TTL by construction and losing them costs a re-share.
  #
  # The whole recovery plan is one asymmetry: every in-cluster object and the entire routing
  # layer rebuild from Git in minutes; the domain registrations and THIS DATA do not.
  transaction_log_retention_days = 7
  retained_backups               = 30
  backup_start_time_utc          = "02:00"
  backup_location                = include.root.locals.region

  maintenance_day          = 7 # Sunday
  maintenance_hour_utc     = 3
  maintenance_update_track = "stable"

  query_insights_enabled = true

  database_flags = {
    # Log any statement over a second. The streaming tier's failure mode is connection-pool
    # exhaustion presenting as latency on unrelated requests, and this is the signal that
    # separates "a query got slow" from "the pool is full".
    "log_min_duration_statement" = "1000"

    # Cap connections below what the tier can actually serve, so that over-capacity is a clean
    # refusal rather than a pool that never drains. The streaming tier holds long-lived,
    # mostly-idle connections — it is the one workload that can exhaust this without any
    # corresponding CPU load.
    "max_connections" = "200"
  }

  databases = {
    studio = {}
  }

  # ---------------------------------------------------------------------------------------
  # IAM database authentication — no passwords, anywhere
  # ---------------------------------------------------------------------------------------
  # There is no password to rotate, to leak, or to find in a state file. The workload
  # authenticates as its Workload Identity principal and Cloud SQL checks IAM.
  #
  # The names are the GCP service accounts these Kubernetes service accounts map to. A
  # mismatch here fails at connection time with an authentication error naming the principal,
  # which is at least legible.
  iam_database_users = [
    {
      name = "studio-bff@${dependency.shared.outputs.project_ids["platform"]}.iam"
      type = "CLOUD_IAM_SERVICE_ACCOUNT"
    },
    {
      name = "studio-bff-stream@${dependency.shared.outputs.project_ids["platform"]}.iam"
      type = "CLOUD_IAM_SERVICE_ACCOUNT"
    },
  ]

  # ---------------------------------------------------------------------------------------
  # Cross-region replica
  # ---------------------------------------------------------------------------------------
  # This Gateway is regional and this is a single-cluster design, so a region loss is an
  # OUTAGE. Whether it is also DATA LOSS depends entirely on this replica existing.
  #
  # Written down rather than assumed, so that it is a decision someone can revisit rather than
  # an oversight discovered during one.
  read_replicas = {
    dr = {
      region       = "europe-west1"
      tier         = "db-custom-2-7680"
      kms_key_name = null
    }
  }

  environment         = local.env
  owner               = "platform"
  data_classification = "confidential"
  labels              = include.root.locals.common_labels
}
