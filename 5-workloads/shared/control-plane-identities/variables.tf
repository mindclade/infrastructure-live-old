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
