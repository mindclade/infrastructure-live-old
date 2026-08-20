# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Project factory — inference serving.
#
# The only domain in the estate carrying customer traffic, which changes two things: an
# outage here is customer-visible rather than internal, and its production budget is expected
# to grow rather than being a sign something is wrong.

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
  config_path                             = "../../../2-environments/development/folders"
  mock_outputs                            = { folder_ids = { serving = "folders/000000000000" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "vpc" {
  config_path = "../../../3-networks/development/shared-vpc-host"

  mock_outputs = {
    host_project_ids = {
      development = "mc-development-net"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id   = "${include.root.locals.prefix}-${include.root.locals.environment}-serving"
  project_name = "${include.root.locals.environment} serving"

  # The per-environment workload-domain folder owned by infrastructure-live. This is what makes "grant the
  # serving team rights over serving in development and nothing else" a single folder
  # binding rather than a project list that goes stale.
  folder_id = dependency.folders.outputs.folder_ids["serving"]

  environment         = include.root.locals.environment
  owner               = "serving"
  data_classification = "internal"

  # Every domain project but `security` is a Shared VPC service project. A workload with its
  # own VPC is a workload outside every firewall rule in 3-networks and outside every VPC-SC
  # perimeter, and nothing about the project says so.
  shared_vpc_host_project_id = dependency.vpc.outputs.host_project_ids["development"]

  # The default compute service account holds roles/editor on its own project. bootstrap
  # already denies the automatic grant org-wide; this deprivileges the account itself, so
  # nothing can fall back to it when a Workload Identity binding is missing.
  remove_default_service_account = true

  activate_apis = concat(include.envcommon.locals.base_services, [
    # Model artefacts served from the registry rather than baked into an image, so a weight
    # update is not a rebuild.
    "artifactregistry.googleapis.com",
    # Request and latency telemetry beyond what the cluster reports.
    "cloudtrace.googleapis.com",
    # Cloud Armor policies on the external ingress.
    "compute.googleapis.com",
    "networksecurity.googleapis.com",
  ])

  # Production serving spend tracks traffic, so growth is expected and an alert at the
  # organization threshold would fire every month for the right reason. The budget below is a
  # shape check rather than a limit — a step change means something other than traffic did.
  monthly_budget_usd = 2000
}
