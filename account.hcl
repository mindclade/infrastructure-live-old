# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Stable, non-secret runtime contract. Ring-0 identifiers are supplied through the process
# environment by protected CI or by sourcing .account.env locally. No company identifiers,
# credentials, or generated state are committed here.
locals {
  org_id                      = get_env("GCP_ORG_ID")
  billing_account             = upper(get_env("BILLING_ACCOUNT"))
  cloud_identity_customer_id  = get_env("CLOUD_IDENTITY_CUSTOMER_ID")
  org_policy_activation_phase = get_env("ORG_POLICY_ACTIVATION_PHASE", "baseline")
  domain                      = get_env("DOMAIN", "mindclade.com")
  prefix                      = get_env("RESOURCE_PREFIX", "mc")
  residency_profile           = get_env("RESIDENCY_PROFILE", "us-only-v1")
  region                      = get_env("PRIMARY_REGION", "us-central1")
  gpu_zone                    = get_env("GPU_ZONE", "${local.region}-b")
  dr_region                   = get_env("DR_REGION", "us-east4")
  dr_gpu_zone                 = get_env("DR_GPU_ZONE", "${local.dr_region}-b")

  seed_project_id      = get_env("BOOTSTRAP_SEED_PROJECT_ID")
  cicd_project_id      = get_env("BOOTSTRAP_CICD_PROJECT_ID")
  cicd_project_number  = get_env("BOOTSTRAP_CICD_PROJECT_NUMBER")
  state_location       = get_env("STATE_LOCATION", "US")
  github_wif_pool_name = get_env("GITHUB_WIF_POOL_NAME")
  # Bootstrap owns provider conditions. This repository creates the six normal-plane service
  # accounts and binds each only to the matching exact principal in this contract.
  # `plan.yml` maps these from repository variables, so the process always carries the names —
  # an unset variable arrives as the empty string, not as an absent one, and `get_env`'s own
  # default therefore never fires. coalesce() covers both, which is what lets the credential-free
  # `validate` job parse every unit instead of failing before it reads a single resource.
  #
  # This does not relax the contract. 1-org/automation-iam types and validates both values, so an
  # empty decode is rejected there: plan and apply still fail closed until the applied bootstrap
  # outputs are exported.
  artifact_release_identities    = jsondecode(coalesce(get_env("ARTIFACT_RELEASE_IDENTITIES_JSON", ""), "{}"))
  dr_evidence_identity           = jsondecode(coalesce(get_env("DR_EVIDENCE_IDENTITY_JSON", ""), "{}"))
  bazel_cache_identity           = jsondecode(coalesce(get_env("BAZEL_CACHE_IDENTITY_JSON", ""), "{}"))
  workstation_image_identity     = jsondecode(coalesce(get_env("WORKSTATION_IMAGE_IDENTITY_JSON", ""), "{}"))
  workstation_image_source_uri   = get_env("WORKSTATION_IMAGE_SOURCE_URI", "")
  workstation_image_source_state = get_env("WORKSTATION_IMAGE_SOURCE_STATE", "blocked")
  workstation_image_source_object_generation = get_env(
    "WORKSTATION_IMAGE_SOURCE_OBJECT_GENERATION",
    "",
  )
  workstation_image_source_sha256   = get_env("WORKSTATION_IMAGE_SOURCE_SHA256", "")
  workstation_image_contract_sha256 = get_env("WORKSTATION_IMAGE_CONTRACT_SHA256", "")
  production_qualification_identity = jsondecode(
    coalesce(get_env("PRODUCTION_QUALIFICATION_IDENTITY_JSON", ""), "{}"),
  )
  bootstrap_account_handoff = jsondecode(
    coalesce(get_env("BOOTSTRAP_ACCOUNT_HANDOFF_JSON", ""), "{}"),
  )

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

  github_org = get_env("MONOREPO_ORG", "mindclade")
}
