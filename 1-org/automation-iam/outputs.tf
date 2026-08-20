# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

output "environment_apply_authority" {
  description = "Environment to scoped apply identity and folder."
  value = {
    for environment, folder in var.environment_folder_ids : environment => {
      folder          = folder
      service_account = var.environment_apply_service_accounts[environment]
    }
  }
}

output "supply_chain_service_accounts" {
  description = "Normal-plane builder/qualifier/signer/promoter service-account emails."
  value       = { for name, sa in google_service_account.supply_chain : name => sa.email }
}

output "artifact_signer_identity_contract" {
  description = "Non-secret identity values consumed by github-config and the protected signer workflow."
  value = {
    WIF_PROVIDER_SIGNER              = var.artifact_signer_wif_provider
    SA_ARTIFACT_SIGNER               = google_service_account.supply_chain["signer"].email
    ARTIFACT_SIGNER_PRINCIPAL        = var.artifact_signer_principal
    ARTIFACT_SIGNER_JOB_WORKFLOW_REF = var.artifact_signer_job_workflow_ref
  }
}
