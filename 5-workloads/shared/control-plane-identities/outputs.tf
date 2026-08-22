# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

output "service_accounts" {
  description = "Normal-plane GitOps render and verification service-account emails."
  value = {
    gitops_render                   = google_service_account.gitops_render.email
    gitops_verifier                 = google_service_account.gitops_verifier.email
    production_qualification_evaluator = google_service_account.production_qualification["evaluator"].email
    production_qualification_reader = google_service_account.production_qualification["reader"].email
    production_qualification_writer = google_service_account.production_qualification["writer"].email
  }
}

output "github_config_identity_handoff" {
  description = "Exact non-secret variables that github-config must re-export after this unit is applied."
  value = {
    SA_GITOPS_RENDER                   = google_service_account.gitops_render.email
    SA_GITOPS_VERIFIER                 = google_service_account.gitops_verifier.email
    SA_PRODUCTION_QUALIFICATION_EVALUATOR = google_service_account.production_qualification["evaluator"].email
    SA_PRODUCTION_QUALIFICATION_READER = google_service_account.production_qualification["reader"].email
    SA_PRODUCTION_QUALIFICATION_WRITER = google_service_account.production_qualification["writer"].email
  }
}

output "secret_resource_names" {
  description = "Secret containers only. Secret versions are injected out of band and never enter Terraform state."
  value = {
    render                   = google_secret_manager_secret.github_app_render_pem.name
    arc_private_key          = google_secret_manager_secret.github_app_arc_pem.name
    arc_app_id               = google_secret_manager_secret.github_app_arc_id.name
    arc_installation_id      = google_secret_manager_secret.github_app_arc_installation_id.name
    arc_promoter             = google_secret_manager_secret.github_app_promoter_pem.name
    production_qualification = google_secret_manager_secret.github_app_production_qualification_pem.name
  }
}

output "production_qualification_identity_handoff" {
  description = "Non-secret WIF, identity, project, and secret identifiers for protected qualification."
  value = {
    WIF_PROVIDER_PRODUCTION_QUALIFICATION       = var.production_qualification_identity.workload_identity_provider
    SA_PRODUCTION_QUALIFICATION_EVALUATOR       = google_service_account.production_qualification["evaluator"].email
    SA_PRODUCTION_QUALIFICATION_READER          = google_service_account.production_qualification["reader"].email
    SA_PRODUCTION_QUALIFICATION_WRITER          = google_service_account.production_qualification["writer"].email
    PRODUCTION_QUALIFICATION_PROJECT            = var.security_project_id
    PRODUCTION_QUALIFICATION_PRIVATE_KEY_SECRET = google_secret_manager_secret.github_app_production_qualification_pem.secret_id
    PRODUCTION_ELIGIBILITY_SIGNING_KEY_ID        = "production-eligibility-v1"
    PRODUCTION_ELIGIBILITY_KMS_KEY_VERSION       = google_kms_crypto_key_version.production_eligibility.name
  }
}

output "production_qualification_identity_contract" {
  description = "Applied bootstrap WIF contract for fail-closed handoff verification."
  value       = var.production_qualification_identity
}

output "github_config_arc_secret_handoff" {
  description = "Non-secret promoter Secret Manager identifiers for GitHub variables."
  value = {
    ARC_PROMOTER_SECRET_PROJECT     = var.security_project_id
    ARC_PROMOTER_PRIVATE_KEY_SECRET = google_secret_manager_secret.github_app_promoter_pem.secret_id
  }
}
