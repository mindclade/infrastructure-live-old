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
    render = google_secret_manager_secret.github_app_render_pem.name
  }
}
