# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Per-environment shared projects and budgets.
#
# "Shared" means shared BY the workload projects in this environment, not shared BETWEEN
# environments. Nothing here is reachable from another environment, which is the property
# that makes an environment a boundary rather than a naming convention.
#
# Two projects, and the split is the point:
#
#   <prefix>-<env>-net    the Shared VPC host. 3-networks builds the network inside it.
#   <prefix>-<env>-ops    shared operational surface: monitoring scope, DNS zones, the
#                         environment's Artifact Registry mirrors.
#
# The host project holds no workloads at all. A workload in a host project gets ambient
# network admin over every service project attached to it, and the grant is invisible from
# the service project's own IAM.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/shared-projects.hcl"
  expose         = true
  merge_strategy = "deep"
}

# The environment parent folder is created by infrastructure-live/1-org/folders. Reading the
# output here establishes both the project parent and the dependency order for run queues.
dependency "folders" {
  config_path = "../../../1-org/folders"

  mock_outputs = {
    folder_ids = { development = "folders/000000000000" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  folder_id = dependency.folders.outputs.folder_ids["development"]
  # Development runs the whole estate's experiments and is the environment where a runaway
  # job is most likely and least noticed. Deliberately the tightest budget of the three:
  # production spending more than expected is a business event, development spending more
  # than expected is a mistake.
  budget_amount = 8000

  # Development is where an upgrade or a quota change should surface first, so its ops
  # project enables the preview APIs the other environments do not.
  extra_services = [
    "gkehub.googleapis.com",
    "anthosconfigmanagement.googleapis.com",
  ]
}
