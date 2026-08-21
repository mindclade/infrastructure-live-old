# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

variable "security_project_id" {
  type        = string
  description = "Common security project that owns control-plane identities and secret containers."
}

variable "region" {
  type        = string
  description = "Residency-approved Secret Manager replica region."
}

variable "secret_kms_key_id" {
  type        = string
  description = "CMEK used for control-plane secret containers."
}

variable "github_wif_pool_name" {
  type        = string
  description = "Bootstrap-managed GitHub workload identity pool resource name."
  validation {
    condition     = can(regex("^projects/[0-9]+/locations/global/workloadIdentityPools/[a-z0-9-]+$", var.github_wif_pool_name))
    error_message = "github_wif_pool_name must be a full workload identity pool resource name."
  }
}

variable "github_org" {
  type        = string
  description = "Canonical GitHub organization login."
}

variable "production_qualification_identity" {
  description = "Bootstrap-exported exact WIF provider and principal for GitOps production qualification."
  type = object({
    workload_identity_provider = string
    principal                  = string
    subject                    = string
    workflow_ref               = string
  })
  validation {
    condition = (
      can(regex("^projects/[0-9]+/locations/global/workloadIdentityPools/github/providers/gh-production-qualification$", var.production_qualification_identity.workload_identity_provider)) &&
      can(regex("^principal://iam\\.googleapis\\.com/projects/[0-9]+/locations/global/workloadIdentityPools/github/subject/production-qualification:repo:mindclade@[0-9]+/gitops@[0-9]+:environment:production$", var.production_qualification_identity.principal)) &&
      can(regex("^repo:mindclade@[0-9]+/gitops@[0-9]+:environment:production$", var.production_qualification_identity.subject)) &&
      var.production_qualification_identity.workflow_ref == "mindclade/gitops/.github/workflows/production-qualification-evidence.yml@refs/heads/main"
    )
    error_message = "Production qualification identity must match the exact protected GitOps workflow contract."
  }
}

variable "ci_project_id" {
  type        = string
  description = "Project that owns the private ARC GKE cluster."
}

variable "ci_project_number" {
  type        = string
  description = "Numeric project number used in the exact GKE workload principal."
}

variable "arc_promoter_service_account_email" {
  type        = string
  description = "Normal-plane promoter identity that may read only its GitHub App key."
}

variable "platform_project_ids" {
  type = object({
    development = string
    staging     = string
    production  = string
  })
  description = "Environment platform projects containing Artifact Registry and Binary Authorization resources."
}
