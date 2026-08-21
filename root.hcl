# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Root Terragrunt configuration inherited by every live unit.
locals {
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  environment = try(
    read_terragrunt_config(find_in_parent_folders("env.hcl")).locals.environment,
    "global",
  )
  region = try(
    read_terragrunt_config(find_in_parent_folders("env.hcl")).locals.region,
    local.account_vars.locals.region,
  )

  org_id                      = local.account_vars.locals.org_id
  billing_account             = local.account_vars.locals.billing_account
  cloud_identity_customer_id  = local.account_vars.locals.cloud_identity_customer_id
  org_policy_activation_phase = local.account_vars.locals.org_policy_activation_phase
  domain                      = local.account_vars.locals.domain
  prefix                      = local.account_vars.locals.prefix
  residency_profile           = local.account_vars.locals.residency_profile
  dr_region                   = local.account_vars.locals.dr_region
  dr_gpu_zone                 = local.account_vars.locals.dr_gpu_zone
  seed_project_id             = local.account_vars.locals.seed_project_id
  cicd_project_id             = local.account_vars.locals.cicd_project_id
  cicd_project_number         = local.account_vars.locals.cicd_project_number
  state_location              = local.account_vars.locals.state_location
  github_org                  = local.account_vars.locals.github_org

  module_source_org  = "mindclade"
  module_source_repo = "mindclade-internal-monorepo"
  module_source_base = "git::https://github.com/${local.module_source_org}/${local.module_source_repo}.git//infra/terraform/modules"

  # Organization/shared units use the production/foundation state bucket. Environment units
  # use their own bucket, matching the bootstrap-created plan/apply identities.
  state_scope  = contains(["development", "staging"], local.environment) ? local.environment : "production"
  state_bucket = local.account_vars.locals.state_buckets[local.state_scope]

  relative_path = path_relative_to_include()
  common_labels = {
    managed-by  = "terragrunt"
    repository  = "infrastructure-live"
    environment = local.environment
    unit        = replace(local.relative_path, "/", "-")
  }
}

remote_state {
  backend = "gcs"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    bucket                    = local.state_bucket
    prefix                    = local.relative_path
    project                   = local.seed_project_id
    location                  = local.state_location
    skip_bucket_creation      = true
    enable_bucket_policy_only = true
  }
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<-EOF
    provider "google" {
      region         = "${local.region}"
      default_labels = ${jsonencode(local.common_labels)}
      request_timeout = "120s"
    }
    provider "google-beta" {
      region         = "${local.region}"
      default_labels = ${jsonencode(local.common_labels)}
      request_timeout = "120s"
    }
  EOF
}

generate "versions" {
  path      = "versions_override.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<-EOF
    terraform {
      required_version = ">= 1.15.0, < 1.16.0"
      required_providers {
        google = {
          source  = "hashicorp/google"
          version = "= 7.41.0"
        }
        google-beta = {
          source  = "hashicorp/google-beta"
          version = "= 7.41.0"
        }
      }
    }
  EOF
}

terraform {
  extra_arguments "lock" {
    commands  = ["init"]
    arguments = ["-lockfile=readonly"]
  }
  extra_arguments "retry_lock" {
    commands  = get_terraform_commands_that_need_locking()
    arguments = ["-lock-timeout=20m"]
  }
}

errors {
  retry "transient" {
    retryable_errors = [
      "(?s).*Error 500.*",
      "(?s).*Error 502.*",
      "(?s).*Error 503.*",
      "(?s).*connection reset by peer.*",
      "(?s).*TLS handshake timeout.*",
      "(?s).*Error waiting for.*",
      "(?s).*is not ready.*",
    ]
    max_attempts       = 3
    sleep_interval_sec = 10
  }
}
