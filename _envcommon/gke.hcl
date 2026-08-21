# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Shared GKE defaults. Included by every 5-workloads/<env>/gke unit, which overrides only
# what genuinely differs between environments.
#
# The point of _envcommon is that a hardening default set here cannot be forgotten in one
# environment. If production has a control that staging does not, staging stops being a
# useful rehearsal.

locals {
  root         = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  environment = local.env_vars.locals.environment

  # Protected release candidate. The tag is published only after repository and connected
  # plan evidence for the complete typed interface set is approved.
  module_version = "v0.4.0"

  # Control-plane peering ranges are deliberately outside the VPC, Pod, Service, and ARC
  # allocations. Changing one recreates the private control-plane peering contract.
  master_ipv4_cidrs = {
    development = "10.240.0.0/28"
    staging     = "10.241.0.0/28"
    production  = "10.242.0.0/28"
  }

  node_cidrs = {
    development = "10.16.0.0/20"
    staging     = "10.32.0.0/20"
    production  = "10.48.0.0/20"
  }
}

terraform {
  source = "${local.root.locals.module_source_base}//gke?ref=${local.module_version}"
}

inputs = {
  name   = "${local.account_vars.locals.prefix}-${local.environment}"
  region = local.account_vars.locals.region

  master_ipv4_cidr_block = local.master_ipv4_cidrs[local.environment]
  master_authorized_networks = [{
    cidr_block   = local.node_cidrs[local.environment]
    display_name = "${local.environment}-private-nodes"
  }]

  rbac_security_group = "gke-security-groups@${local.account_vars.locals.domain}"
  environment         = local.environment
  owner               = "platform"
  data_classification = "confidential"

  # Development receives upgrades first. Staging and production remain on the same qualified
  # channel so staging is a faithful rehearsal instead of a different lifecycle policy.
  release_channel = local.environment == "development" ? "RAPID" : "REGULAR"
  channel_policy  = local.environment == "development" ? "CANARY" : "QUALIFIED"

  # NOVA mounts model artifacts through generation-bound object APIs. GCS Fuse remains off
  # until an independently qualified platform lock says otherwise.
  enable_gcs_fuse_csi_driver    = false
  enable_backup_agent           = true
  enable_secret_sync            = true
  secret_sync_rotation_interval = "120s"

  maintenance_window = {
    # Production maintains at the weekend; everything else on weekday nights, so a surprise
    # from an upgrade surfaces in a lower environment first.
    start_time = local.environment == "production" ? "2026-01-03T02:00:00Z" : "2026-01-01T01:00:00Z"
    end_time   = local.environment == "production" ? "2026-01-03T10:00:00Z" : "2026-01-01T09:00:00Z"
    recurrence = local.environment == "production" ? "FREQ=WEEKLY;BYDAY=SA,SU" : "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH"
  }

  system_node_pool_machine_type      = "n2-standard-8"
  system_node_pool_total_min_nodes   = 3
  system_node_pool_total_max_nodes   = local.environment == "production" ? 12 : 6
  system_node_pool_max_pods_per_node = 64
  system_node_pool_boot_disk_size_gb = 100

  resource_labels = merge(local.root.locals.common_labels, {
    authority = "terraform"
    workload  = "platform"
  })
}
