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
      var.dr_evidence_identity.job_workflow_ref == "mindclade/.github/.github/workflows/reusable-dr-evidence.yml@refs/tags/v5.0.0" &&
      toset(keys(var.dr_evidence_identity.principals)) == toset([
        "bootstrap:scratch", "bootstrap:staging", "github-config:scratch", "github-config:staging",
        "infrastructure-live:scratch", "infrastructure-live:staging", "gitops:scratch", "gitops:staging",
      ])
    )
    error_message = "dr_evidence_identity must match the bootstrap DR evidence contract and contain exactly eight protected caller principals."
  }
}

variable "bazel_cache_identity" {
  description = "Bootstrap-exported dedicated provider and exact Bazel cache access routes."
  type = object({
    workload_identity_provider = string
    repository                 = string
    repository_owner_id        = string
    repository_id              = string
    routes = map(object({
      access        = string
      event_name    = string
      principal     = string
      ref_policy    = string
      workflow_path = string
    }))
  })

  validation {
    condition = try(
      var.bazel_cache_identity.workload_identity_provider == "${var.github_wif_pool_name}/providers/gh-bazel-cache" &&
      var.bazel_cache_identity.repository == "${var.github_org}/mindclade-internal-monorepo" &&
      can(regex("^[0-9]+$", var.bazel_cache_identity.repository_owner_id)) &&
      can(regex("^[0-9]+$", var.bazel_cache_identity.repository_id)) &&
      toset(keys(var.bazel_cache_identity.routes)) == toset([
        "pull-request-read", "trusted-main-write", "merge-group-write", "nightly-write",
      ]) &&
      alltrue([
        for route, expected in {
          pull-request-read = {
            access        = "read"
            event_name    = "pull_request"
            ref_policy    = "pull-request-merge"
            workflow_path = "${var.github_org}/mindclade-internal-monorepo/.github/workflows/presubmit.yml"
          }
          trusted-main-write = {
            access        = "write"
            event_name    = "push"
            ref_policy    = "protected-main"
            workflow_path = "${var.github_org}/mindclade-internal-monorepo/.github/workflows/presubmit.yml"
          }
          merge-group-write = {
            access        = "write"
            event_name    = "merge_group"
            ref_policy    = "protected-merge-queue"
            workflow_path = "${var.github_org}/mindclade-internal-monorepo/.github/workflows/presubmit.yml"
          }
          nightly-write = {
            access        = "write"
            event_name    = "schedule"
            ref_policy    = "protected-main"
            workflow_path = "${var.github_org}/mindclade-internal-monorepo/.github/workflows/nightly.yml"
          }
        } :
        var.bazel_cache_identity.routes[route].access == expected.access &&
        var.bazel_cache_identity.routes[route].event_name == expected.event_name &&
        var.bazel_cache_identity.routes[route].ref_policy == expected.ref_policy &&
        var.bazel_cache_identity.routes[route].workflow_path == expected.workflow_path &&
        var.bazel_cache_identity.routes[route].principal == "principal://iam.googleapis.com/${var.github_wif_pool_name}/subject/bazel-cache:${route}"
      ]),
      false,
    )
    error_message = "bazel_cache_identity must match the exact bootstrap contract 2.0.0 provider, repository, and read/write routes."
  }
}

variable "workstation_image_identity" {
  description = "Bootstrap-exported dedicated provider and exact immutable workstation-image publisher identity."
  type = object({
    workload_identity_provider = string
    principal                  = string
    repository                 = string
    repository_id              = string
    subject                    = string
    workflow_ref               = string
    job_workflow_ref           = string
  })

  validation {
    condition = try(
      var.workstation_image_identity.workload_identity_provider == "${var.github_wif_pool_name}/providers/gh-workstation-image" &&
      var.workstation_image_identity.repository == "${var.github_org}/mindclade-internal-monorepo" &&
      can(regex("^[0-9]+$", var.workstation_image_identity.repository_id)) &&
      can(regex("^repo:${var.github_org}@[0-9]+/mindclade-internal-monorepo@[0-9]+:environment:workstation-image-publication$", var.workstation_image_identity.subject)) &&
      var.workstation_image_identity.principal == "principal://iam.googleapis.com/${var.github_wif_pool_name}/subject/workstation-image:${var.workstation_image_identity.subject}" &&
      var.workstation_image_identity.workflow_ref == "${var.github_org}/mindclade-internal-monorepo/.github/workflows/nixos-image.yml@refs/heads/main" &&
      var.workstation_image_identity.job_workflow_ref == "${var.github_org}/.github/.github/workflows/reusable-nixos-gce-image-publish.yml@refs/tags/v5.0.0",
      false,
    )
    error_message = "workstation_image_identity must match bootstrap contract 2.0.0 and the exact protected caller/reusable workflow pair."
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
