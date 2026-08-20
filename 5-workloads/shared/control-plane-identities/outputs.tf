# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

output "service_accounts" {
  description = "Normal-plane GitOps render and verification service-account emails."
  value = {
    gitops_render   = google_service_account.gitops_render.email
    gitops_verifier = google_service_account.gitops_verifier.email
  }
}

output "github_config_identity_handoff" {
  description = "Exact non-secret variables that github-config must re-export after this unit is applied."
  value = {
    SA_GITOPS_RENDER   = google_service_account.gitops_render.email
    SA_GITOPS_VERIFIER = google_service_account.gitops_verifier.email
  }
}

output "secret_resource_names" {
  description = "Secret containers only. Secret versions are injected out of band and never enter Terraform state."
  value = {
    render              = google_secret_manager_secret.github_app_render_pem.name
    arc_private_key     = google_secret_manager_secret.github_app_arc_pem.name
    arc_app_id          = google_secret_manager_secret.github_app_arc_id.name
    arc_installation_id = google_secret_manager_secret.github_app_arc_installation_id.name
    arc_promoter        = google_secret_manager_secret.github_app_promoter_pem.name
  }
}

output "github_config_arc_secret_handoff" {
  description = "Non-secret promoter Secret Manager identifiers for GitHub variables."
  value = {
    ARC_PROMOTER_SECRET_PROJECT     = var.security_project_id
    ARC_PROMOTER_PRIVATE_KEY_SECRET = google_secret_manager_secret.github_app_promoter_pem.secret_id
  }
}
