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

variable "buildkite_wif_pool_name" {
  type        = string
  description = "Bootstrap-managed Buildkite workload identity pool resource name."
  validation {
    condition     = can(regex("^projects/[0-9]+/locations/global/workloadIdentityPools/buildkite$", var.buildkite_wif_pool_name))
    error_message = "buildkite_wif_pool_name must be the bootstrap-managed Buildkite WIF pool."
  }
}

variable "github_wif_pool_name" {
  type        = string
  description = "Bootstrap-managed GitHub workload identity pool resource name."
  validation {
    condition     = can(regex("^projects/[0-9]+/locations/global/workloadIdentityPools/github$", var.github_wif_pool_name))
    error_message = "github_wif_pool_name must be the bootstrap-managed GitHub WIF pool."
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

variable "artifact_signer_wif_provider" {
  type        = string
  description = "Bootstrap signer-only WIF provider published to GitHub as WIF_PROVIDER_SIGNER."
}

variable "artifact_signer_principal" {
  type        = string
  description = "Bootstrap output for the exact monorepo release-environment WIF subject."
}

variable "artifact_signer_job_workflow_ref" {
  type        = string
  description = "Exact immutable reusable signer workflow enforced by the WIF provider."
}
