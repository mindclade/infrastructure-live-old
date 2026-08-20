# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# Stable, non-secret runtime contract. Ring-0 identifiers are supplied through the process
# environment by protected CI or by sourcing .account.env locally. No company identifiers,
# credentials, or generated state are committed here.
locals {
  org_id          = get_env("GCP_ORG_ID")
  billing_account = upper(get_env("BILLING_ACCOUNT"))
  domain          = get_env("DOMAIN", "mindclade.com")
  prefix          = get_env("RESOURCE_PREFIX", "mc")
  region          = get_env("PRIMARY_REGION", "us-central1")

  seed_project_id      = get_env("BOOTSTRAP_SEED_PROJECT_ID")
  cicd_project_id      = get_env("BOOTSTRAP_CICD_PROJECT_ID")
  cicd_project_number  = get_env("BOOTSTRAP_CICD_PROJECT_NUMBER")
  state_location       = get_env("STATE_LOCATION", "US")
  github_wif_pool_name   = get_env("GITHUB_WIF_POOL_NAME")
  buildkite_wif_pool_name = get_env("BUILDKITE_WIF_POOL_NAME")

  infrastructure_live_service_accounts = {
    plan        = get_env("SA_TF_LIVE_PLAN")
    foundation  = get_env("SA_TF_LIVE_APPLY_FOUNDATION")
    development = get_env("SA_TF_LIVE_APPLY_DEVELOPMENT")
    staging     = get_env("SA_TF_LIVE_APPLY_STAGING")
    production  = get_env("SA_TF_LIVE_APPLY_PRODUCTION")
  }

  state_buckets = {
    development = get_env("TFSTATE_BUCKET_DEVELOPMENT")
    staging     = get_env("TFSTATE_BUCKET_STAGING")
    production  = get_env("TFSTATE_BUCKET_PRODUCTION")
  }

  github_org = get_env("MONOREPO_ORG", "Mindclade")
}
