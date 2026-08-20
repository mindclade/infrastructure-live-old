# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
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

  # Bumping this is a reviewable one-line change that says exactly which module version
  # moved. That is the whole reason modules are pinned by tag rather than tracked by branch.
  module_version = "v0.1.1"
}

terraform {
  source = "${local.root.locals.module_source_base}//gke?ref=${local.module_version}"
}

inputs = {
  name     = "${local.account_vars.locals.prefix}-${local.environment}"
  location = local.account_vars.locals.region

  # Private cluster. Nodes have no public IPs — which is enforced org-wide anyway by
  # compute.vmExternalIpAccess, so a public cluster would simply fail to create.
  enable_private_nodes    = true
  enable_private_endpoint = true  # control plane is reachable only through private connectivity

  # Shielded nodes: secure boot, integrity monitoring, vTPM. Costs nothing and blocks a
  # class of node-level persistence.
  enable_shielded_nodes = true

  # Workload Identity. The Kubernetes-side equivalent of the WIF rule in bootstrap: pods get
  # short-lived tokens for a Google service account instead of a mounted key.
  enable_workload_identity = true

  # Policy Controller (Gatekeeper). The gitops repo's policy/ directory is inert without it.
  enable_policy_controller = true

  # Binary Authorization is configured per-environment in its own unit; this switch is what
  # makes the cluster consult it at admission time.
  enable_binary_authorization = true

  release_channel = local.environment == "development" ? "RAPID" : local.environment == "staging" ? "REGULAR" : "STABLE"

  # Deletion protection on production. Terraform will otherwise delete and recreate a
  # cluster to resolve certain diffs, and the first anyone knows is that the workloads are
  # gone.
  deletion_protection = local.environment == "production"

  enable_managed_prometheus = true
  logging_components        = ["SYSTEM_COMPONENTS", "WORKLOADS", "APISERVER", "CONTROLLER_MANAGER", "SCHEDULER"]
  monitoring_components     = ["SYSTEM_COMPONENTS", "APISERVER", "CONTROLLER_MANAGER", "SCHEDULER"]

  # Application-layer secrets encryption with a CMEK from 1-org/kms.
  database_encryption_state = "ENCRYPTED"

  maintenance_window = {
    # Production maintains at the weekend; everything else on weekday nights, so a surprise
    # from an upgrade surfaces in a lower environment first.
    start_time = local.environment == "production" ? "2026-01-03T02:00:00Z" : "2026-01-01T01:00:00Z"
    end_time   = local.environment == "production" ? "2026-01-03T10:00:00Z" : "2026-01-01T09:00:00Z"
    recurrence = local.environment == "production" ? "FREQ=WEEKLY;BYDAY=SA,SU" : "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH"
  }

  labels = local.root.locals.common_labels
}
