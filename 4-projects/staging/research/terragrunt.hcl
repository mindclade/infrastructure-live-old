# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Project factory — research workloads.
#
# Holds the training corpora, the checkpoints, and the experiment metadata. Not the compute:
# training runs on the shared cluster's GPU pools in 5-workloads, and reaches these buckets
# as a Workload Identity principal.
#
# The rule that makes this project different from the others: the held-out evaluation data is
# NOT here. It lives in its own bucket with an IAM DENY on every training identity — see
# 5-workloads/<env>/storage/gcs-holdout. A benchmark number is worthless if the holdout set
# leaked into training, and the leak is invisible after the fact.

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
  mock_outputs                            = { folder_ids = { research = "folders/000000000000" } }
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
  project_id   = "${include.root.locals.prefix}-${include.root.locals.environment}-research"
  project_name = "${include.root.locals.environment} research"

  # The per-environment workload-domain folder owned by infrastructure-live. This is what makes "grant the
  # research team rights over research in staging and nothing else" a single folder
  # binding rather than a project list that goes stale.
  folder_id = dependency.folders.outputs.folder_ids["research"]

  environment         = include.root.locals.environment
  owner               = "research"
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
    # Experiment tracking and dataset metadata.
    "bigquery.googleapis.com",
    "notebooks.googleapis.com",
    # Vertex AI for managed training jobs that do not warrant a GKE pod.
    "aiplatform.googleapis.com",
  ])

  # Research is where a runaway job is most likely: an experiment is by definition something
  # nobody has run before, and a GPU pool scaled up by a broken sweep costs more in a weekend
  # than the rest of the estate does in a month.
  #
  # Alerts, never a cap. A cap that halts a training run at 80% of an epoch loses the run.
  monthly_budget_usd = 4000
}
