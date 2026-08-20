# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Live-only control-plane identity wiring. These resources connect the bootstrap-managed
# GitHub WIF pool to normal, non-Ring-0 services owned by infrastructure-live. They are kept
# here rather than in bootstrap so Ring 0 does not accumulate registry, GitOps, or secret
# access. No secret payload is created by Terraform.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "common_projects" {
  config_path = "../../../1-org/common-projects"
  mock_outputs = {
    project_ids     = { security = "mc-common-security", ci = "mc-common-ci" }
    project_numbers = { ci = "000000000001" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "automation" {
  config_path = "../../../1-org/automation-iam"
  mock_outputs = {
    supply_chain_service_accounts = {
      promoter = "sa-artifact-promoter@mc-common-ci.iam.gserviceaccount.com"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "global_kms" {
  config_path = "../../../1-org/kms"
  mock_outputs = {
    crypto_key_ids = { ci_secrets = "projects/mock/locations/us-central1/keyRings/mock/cryptoKeys/ci-secrets" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "development" {
  config_path                             = "../../../2-environments/development/shared-projects"
  mock_outputs                            = { project_ids = { platform = "mc-development-platform" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "staging" {
  config_path                             = "../../../2-environments/staging/shared-projects"
  mock_outputs                            = { project_ids = { platform = "mc-staging-platform" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "production" {
  config_path                             = "../../../2-environments/production/shared-projects"
  mock_outputs                            = { project_ids = { platform = "mc-production-platform" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  security_project_id                = dependency.common_projects.outputs.project_ids["security"]
  region                             = include.root.locals.region
  secret_kms_key_id                  = dependency.global_kms.outputs.crypto_key_ids["ci_secrets"]
  github_wif_pool_name               = include.root.locals.account_vars.locals.github_wif_pool_name
  github_org                         = include.root.locals.github_org
  ci_project_id                      = dependency.common_projects.outputs.project_ids["ci"]
  ci_project_number                  = dependency.common_projects.outputs.project_numbers["ci"]
  arc_promoter_service_account_email = dependency.automation.outputs.supply_chain_service_accounts["promoter"]


  platform_project_ids = {
    development = dependency.development.outputs.project_ids["platform"]
    staging     = dependency.staging.outputs.project_ids["platform"]
    production  = dependency.production.outputs.project_ids["platform"]
  }
}
