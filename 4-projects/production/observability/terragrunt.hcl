# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# Project factory — metrics, logs, traces.
#
# Distinct from the shared `ops` project in 2-environments, and the split is worth stating
# because it is not obvious: `ops` is the METRICS SCOPE — the project every workload writes
# into so one dashboard covers an environment. This project holds the observability STACK:
# alert policies, SLO definitions, dashboards, and the notification channels they fire
# through.
#
# Keeping them apart means an alert policy can be changed without a grant on the project that
# receives every workload's telemetry.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/workload-project.hcl"
  expose         = true
  merge_strategy = "deep"
}

dependency "folders" {
  config_path = "../../../2-environments/production/folders"
  mock_outputs = { folder_ids = { observability = "folders/000000000000" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "vpc" {
  config_path = "../../../3-networks/production/shared-vpc-host"

  mock_outputs = {
    host_project_ids = {
      production = "mc-production-net"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id   = "${include.root.locals.prefix}-${include.root.locals.environment}-observability"
  project_name = "${include.root.locals.environment} observability"

  # The per-environment workload-domain folder owned by infrastructure-live. This is what makes "grant the
  # observability team rights over observability in production and nothing else" a single folder
  # binding rather than a project list that goes stale.
  folder_id = dependency.folders.outputs.folder_ids["observability"]

  environment         = include.root.locals.environment
  owner               = "platform"
  data_classification = "internal"

  # Every domain project but `security` is a Shared VPC service project. A workload with its
  # own VPC is a workload outside every firewall rule in 3-networks and outside every VPC-SC
  # perimeter, and nothing about the project says so.
  shared_vpc_host_project_id = dependency.vpc.outputs.host_project_ids["production"]

  # The default compute service account holds roles/editor on its own project. bootstrap
  # already denies the automatic grant org-wide; this deprivileges the account itself, so
  # nothing can fall back to it when a Workload Identity binding is missing.
  remove_default_service_account = true

  activate_apis = concat(include.envcommon.locals.base_services, [
    "cloudtrace.googleapis.com",
    "cloudprofiler.googleapis.com",
    # Managed Prometheus rule evaluation and the alerting that reads it.
    "monitoring.googleapis.com",
    # Long-window SLO queries against the log-based metrics in 1-org/log-sinks.
    "bigquery.googleapis.com",
  ])

  # Observability cost is dominated by log ingestion, which is governed centrally in
  # 1-org/log-sinks rather than here. A step change in this project's spend usually means a
  # workload started emitting at DEBUG, not that anything in this project changed.
  monthly_budget_usd = 6000
}
