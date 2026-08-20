# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Project factory — lakehouse and pipelines.
#
# The largest data volume in the estate and, consequently, the project where the DATA_READ
# audit config in bootstrap is most expensive and most valuable. That trade-off is settled in
# 1-org/log-sinks: bigquery and storage are both on the DATA_READ list,
# and the training identities are exempted so their constant reads do not bury the ones a
# human should be looking at.

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
  config_path                             = "../../../2-environments/staging/folders"
  mock_outputs                            = { folder_ids = { data = "folders/000000000000" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "vpc" {
  config_path = "../../../3-networks/staging/shared-vpc-host"

  mock_outputs = {
    host_project_ids = {
      staging = "mc-staging-net"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id   = "${include.root.locals.prefix}-${include.root.locals.environment}-data"
  project_name = "${include.root.locals.environment} data"

  # The per-environment workload-domain folder owned by infrastructure-live. This is what makes "grant the
  # data team rights over data in staging and nothing else" a single folder
  # binding rather than a project list that goes stale.
  folder_id = dependency.folders.outputs.folder_ids["data"]

  environment         = include.root.locals.environment
  owner               = "data-platform"
  data_classification = "confidential"

  # Every domain project but `security` is a Shared VPC service project. A workload with its
  # own VPC is a workload outside every firewall rule in 3-networks and outside every VPC-SC
  # perimeter, and nothing about the project says so.
  shared_vpc_host_project_id = dependency.vpc.outputs.host_project_ids["staging"]

  # The default compute service account holds roles/editor on its own project. bootstrap
  # already denies the automatic grant org-wide; this deprivileges the account itself, so
  # nothing can fall back to it when a Workload Identity binding is missing.
  remove_default_service_account = true

  activate_apis = concat(include.envcommon.locals.base_services, [
    "bigquery.googleapis.com",
    "bigquerydatatransfer.googleapis.com",
    "datacatalog.googleapis.com",
    "dataplex.googleapis.com",
    # Pub/Sub carries ingestion events between the pipeline stages that run on the cluster.
    # The topics themselves are declared with the workloads, not here.
    "pubsub.googleapis.com",
  ])

  monthly_budget_usd = 4000
}
