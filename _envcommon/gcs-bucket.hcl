# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Shared GCS defaults.

locals {
  root         = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  environment    = local.env_vars.locals.environment
  module_version = "v0.1.1"
}

terraform {
  source = "${local.root.locals.module_source_base}//storage?ref=${local.module_version}"
}

inputs = {
  location = local.account_vars.locals.region

  # Both enforced org-wide as well. Repeated here so a bucket created from this module is
  # correct even if it lands somewhere the org policy has an exemption.
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning = true

  # CMEK from the environment keyring in 1-org/kms.
  encryption_key = "projects/${local.account_vars.locals.seed_project_id}/locations/${local.account_vars.locals.region}/keyRings/${local.account_vars.locals.prefix}-${local.environment}/cryptoKeys/storage"

  lifecycle_rules = [
    {
      condition = { age = 90, with_state = "ARCHIVED" }
      action    = { type = "Delete" }
    },
    {
      condition = { age = 30, matches_storage_class = ["STANDARD"] }
      action    = { type = "SetStorageClass", storage_class = "NEARLINE" }
    },
  ]

  # Production buckets have soft-delete retention, so an accidental delete is recoverable
  # for a week rather than immediately final.
  soft_delete_retention_seconds = local.environment == "production" ? 604800 : 0

  labels = local.root.locals.common_labels
}
