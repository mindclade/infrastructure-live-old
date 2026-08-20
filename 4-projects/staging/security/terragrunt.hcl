# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# Project factory — security tooling and scanning.
#
# One property distinguishes this project from every other in 4-projects: what runs here
# inspects the rest of the estate, so a compromise of this project is a compromise of the
# thing that would have detected the compromise.
#
# Consequences, both deliberate:
#   - It is NOT a Shared VPC service project. Scanning traffic has no reason to originate
#     inside the workload network, and keeping it out means a lateral move from a workload
#     cannot reach the scanner by network path alone. That is why this unit, alone among the
#     five domains, takes no dependency on 3-networks.
#   - The security team holds admin here and nowhere else. Everywhere else they hold
#     securityReviewer, which reads and cannot change.

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
  config_path = "../../../2-environments/staging/folders"
  mock_outputs = { folder_ids = { security = "folders/000000000000" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id   = "${include.root.locals.prefix}-${include.root.locals.environment}-security"
  project_name = "${include.root.locals.environment} security"

  # The per-environment workload-domain folder owned by infrastructure-live. This is what makes "grant the
  # security team rights over security in staging and nothing else" a single folder
  # binding rather than a project list that goes stale.
  folder_id = dependency.folders.outputs.folder_ids["security"]

  environment         = include.root.locals.environment
  owner               = "security"
  data_classification = "restricted"

  # Deliberately unattached — see the header.
  shared_vpc_host_project_id = null

  # The default compute service account holds roles/editor on its own project. bootstrap
  # already denies the automatic grant org-wide; this deprivileges the account itself, so
  # nothing can fall back to it when a Workload Identity binding is missing.
  remove_default_service_account = true

  activate_apis = concat(include.envcommon.locals.base_services, [
    # Container Analysis holds the vulnerability findings the vuln-scan attestor reads
    # before it will sign — see _envcommon/binauthz.hcl.
    "containeranalysis.googleapis.com",
    "ondemandscanning.googleapis.com",
    # Binary Authorization attestor definitions and their KMS-backed signing keys.
    "binaryauthorization.googleapis.com",
    # Web Security Scanner and SCC findings ingestion.
    "securitycenter.googleapis.com",
    "websecurityscanner.googleapis.com",
  ])

  monthly_budget_usd = 1000
}
