# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# One immutable Docker promotion repository per environment. Language mirrors are separate
# trust and retention boundaries and require their own reviewed modules before activation.

locals {
  root         = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  environment    = local.env_vars.locals.environment
  module_version = "4d5c0105295bf4a01b770fb75f6a8db5c22c8f79"
}

terraform {
  source = "${local.root.locals.module_source_base}//artifact_registry?ref=${local.module_version}"
}

inputs = {
  location            = local.account_vars.locals.region
  repository_id       = "releases"
  description         = "Qualified immutable workload images promoted by digest."
  environment         = local.environment
  owner               = "platform"
  data_classification = "internal"

  # Cleanup remains report-only until a reviewed report proves that rollback and legal
  # retention digests survive the policy.
  cleanup_policy_dry_run   = true
  untagged_retention_days  = 30
  minimum_versions_to_keep = 30

  labels = merge(local.root.locals.common_labels, {
    authority = "artifact-release"
  })
}
