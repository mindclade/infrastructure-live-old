# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Live-only authority handoff. Bootstrap creates the keyless identities; this foundation
# unit grants each environment apply identity permissions only within its own top-level
# folder. The implementation is intentionally local because it binds state owners rather
# than describing a reusable workload resource.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "folders" {
  config_path = "../folders"
  mock_outputs = {
    folder_ids = {
      development = "folders/000000000001"
      staging     = "folders/000000000002"
      production  = "folders/000000000003"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "common_projects" {
  config_path                             = "../common-projects"
  mock_outputs                            = { project_ids = { ci = "mc-common-ci" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  ci_project_id               = dependency.common_projects.outputs.project_ids["ci"]
  github_wif_pool_name        = include.root.locals.account_vars.locals.github_wif_pool_name
  github_org                  = include.root.locals.account_vars.locals.github_org
  artifact_release_identities = include.root.locals.account_vars.locals.artifact_release_identities
  dr_evidence_identity        = include.root.locals.account_vars.locals.dr_evidence_identity
  bazel_cache_identity        = include.root.locals.account_vars.locals.bazel_cache_identity
  workstation_image_identity  = include.root.locals.account_vars.locals.workstation_image_identity

  environment_folder_ids = {
    development = dependency.folders.outputs.folder_ids["development"]
    staging     = dependency.folders.outputs.folder_ids["staging"]
    production  = dependency.folders.outputs.folder_ids["production"]
  }

  environment_apply_service_accounts = {
    development = include.root.locals.account_vars.locals.infrastructure_live_service_accounts.development
    staging     = include.root.locals.account_vars.locals.infrastructure_live_service_accounts.staging
    production  = include.root.locals.account_vars.locals.infrastructure_live_service_accounts.production
  }
}
