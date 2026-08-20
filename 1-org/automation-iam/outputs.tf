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
  description = "Normal-plane ARC capability service-account emails."
  value       = { for name, sa in google_service_account.supply_chain : name => sa.email }
}

output "ci_project_id" {
  description = "Common CI project that owns the normal-plane ARC identities."
  value       = var.ci_project_id
}

output "arc_system_node_service_account" {
  description = "Dedicated private ARC GKE system-node VM identity."
  value       = google_service_account.arc_system_nodes.email
}

output "artifact_signer_identity_contract" {
  description = "Non-secret identity values consumed by github-config and the protected signer workflow."
  value = {
    WIF_PROVIDER_SIGNER              = var.artifact_release_identities["signer"].workload_identity_provider
    SA_ARTIFACT_SIGNER               = google_service_account.supply_chain["signer"].email
    ARTIFACT_SIGNER_PRINCIPAL        = var.artifact_release_identities["signer"].principal
    ARTIFACT_SIGNER_JOB_WORKFLOW_REF = var.artifact_release_identities["signer"].job_workflow_ref
  }
}

output "artifact_release_identity_contract" {
  description = "Applied provider, principal, workflow, and service-account pairing for every ARC capability."
  value = {
    for capability, identity in var.artifact_release_identities : capability => merge(identity, {
      service_account = google_service_account.supply_chain[replace(capability, "-", "_")].email
    })
  }
}

output "github_config_arc_identity_handoff" {
  description = "Exact non-secret ARC service-account variables for github-config."
  value = {
    SA_ARC_CANARY                    = google_service_account.supply_chain["canary"].email
    SA_ARTIFACT_BUILDER              = google_service_account.supply_chain["builder"].email
    SA_ARTIFACT_QUALIFICATION_READER = google_service_account.supply_chain["qualification_reader"].email
    SA_ARTIFACT_QUALIFIER            = google_service_account.supply_chain["qualifier"].email
    SA_ARTIFACT_SIGNER               = google_service_account.supply_chain["signer"].email
    SA_ARTIFACT_PROMOTER             = google_service_account.supply_chain["promoter"].email
  }
}

output "dr_evidence_identity_contract" {
  description = "Protected GitHub environment variables and exact trust contract for DR evidence callers."
  value = {
    WIF_PROVIDER_DR_EVIDENCE = var.dr_evidence_identity.workload_identity_provider
    SA_DR_EVIDENCE_WRITER    = google_service_account.dr_evidence_writer.email
    principals               = var.dr_evidence_identity.principals
    job_workflow_ref         = var.dr_evidence_identity.job_workflow_ref
  }
}
