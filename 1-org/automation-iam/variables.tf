# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

variable "environment_folder_ids" {
  type = object({
    development = string
    staging     = string
    production  = string
  })
  description = "Top-level environment folder resource names."

  validation {
    condition = alltrue([
      for id in values(var.environment_folder_ids) : can(regex("^folders/[0-9]+$", id))
    ])
    error_message = "Every environment folder must use folders/<numeric-id>."
  }
}

variable "environment_apply_service_accounts" {
  type = object({
    development = string
    staging     = string
    production  = string
  })
  description = "Bootstrap-created, environment-scoped infrastructure apply identities."

  validation {
    condition = alltrue([
      for email in values(var.environment_apply_service_accounts) :
      can(regex("^[a-z0-9-]+@[a-z0-9-]+\\.iam\\.gserviceaccount\\.com$", email))
    ])
    error_message = "Every apply identity must be a Google service-account email."
  }
}

variable "ci_project_id" {
  type        = string
  description = "Normal-plane common CI project that owns supply-chain service accounts."
}

variable "github_wif_pool_name" {
  type        = string
  description = "Bootstrap-managed GitHub workload identity pool resource name."
  validation {
    condition     = can(regex("^projects/[0-9]+/locations/global/workloadIdentityPools/github$", var.github_wif_pool_name))
    error_message = "github_wif_pool_name must be the bootstrap-managed GitHub WIF pool."
  }
}

variable "artifact_release_identities" {
  description = "Bootstrap-exported capability-specific ARC provider/principal contracts."
  type = map(object({
    workload_identity_provider = string
    principal                  = string
    subject                    = string
    workflow_ref               = string
    job_workflow_ref           = string
  }))

  validation {
    condition = toset(keys(var.artifact_release_identities)) == toset([
      "canary", "builder", "qualification-reader", "qualifier", "signer", "promoter"
    ])
    error_message = "artifact_release_identities must contain exactly the six ARC release capabilities."
  }
}

variable "dr_evidence_identity" {
  description = "Bootstrap-exported WIF provider and exact scratch/staging principals for DR evidence publication."
  type = object({
    workload_identity_provider = string
    job_workflow_ref           = string
    principals                 = map(string)
  })

  validation {
    condition = (
      can(regex("^projects/[0-9]+/locations/global/workloadIdentityPools/github/providers/gh-dr-evidence$", var.dr_evidence_identity.workload_identity_provider)) &&
      var.dr_evidence_identity.job_workflow_ref == "mindclade/.github/.github/workflows/reusable-dr-evidence.yml@refs/tags/v4.0.0" &&
      toset(keys(var.dr_evidence_identity.principals)) == toset([
        "bootstrap:scratch", "bootstrap:staging", "github-config:scratch", "github-config:staging",
        "infrastructure-live:scratch", "infrastructure-live:staging", "gitops:scratch", "gitops:staging",
      ])
    )
    error_message = "dr_evidence_identity must match bootstrap contract 1.4.0 and contain exactly eight protected caller principals."
  }
}

variable "github_org" {
  type        = string
  description = "GitHub organization whose protected monorepo release workflow may sign."
  validation {
    condition     = can(regex("^[A-Za-z0-9-]+$", var.github_org))
    error_message = "github_org must be a GitHub organization login."
  }
}
