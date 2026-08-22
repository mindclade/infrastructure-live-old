# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

locals {
  root         = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  environment    = local.env_vars.locals.environment
  module_version = "v0.4.0"
}

terraform {
  source = "${local.root.locals.module_source_base}//bazel_remote_cache?ref=${local.module_version}"
}

dependency "shared" {
  config_path = "${get_repo_root()}/2-environments/${local.environment}/shared-projects"
  mock_outputs = {
    project_ids = { platform = "mc-${local.environment}-platform" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "${get_repo_root()}/2-environments/${local.environment}/kms"
  mock_outputs = {
    crypto_key_ids = {
      storage = "projects/mock/locations/${local.account_vars.locals.region}/keyRings/mock-${local.environment}/cryptoKeys/storage"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "access_logs" {
  config_path = "${get_repo_root()}/5-workloads/shared/bazel-cache-access-logs"
  mock_outputs = {
    bucket = { name = "mc-bazel-cache-access-logs" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id               = dependency.shared.outputs.project_ids["platform"]
  bucket_name              = "${local.account_vars.locals.prefix}-${local.environment}-bazel-cache"
  location                 = local.account_vars.locals.region
  kms_key_name             = dependency.kms.outputs.crypto_key_ids["storage"]
  access_log_bucket        = dependency.access_logs.outputs.bucket.name
  access_log_object_prefix = "bazel-remote-cache/${local.environment}/"
  environment              = local.environment
  owner                    = "developer-platform"
  data_classification      = "internal"
  writer_members = [
    "serviceAccount:bazel-remote-executor@${dependency.shared.outputs.project_ids["platform"]}.iam.gserviceaccount.com",
  ]
  cache_ttl_days              = local.environment == "production" ? 30 : 14
  noncurrent_version_ttl_days = 1
  soft_delete_retention_days  = 7
  retention_period_seconds    = 86400
  labels = merge(local.root.locals.common_labels, {
    authority = "terraform"
    workload  = "bazel-remote-execution"
  })
}
