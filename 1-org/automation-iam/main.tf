# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

locals {
  # These permissions are inherited only by one environment folder. Organization-wide
  # policy, DNS, SCC, centralized logging, and shared networking remain exclusive to the
  # foundation apply identity.
  environment_apply_roles = toset([
    "roles/artifactregistry.admin",
    "roles/binaryauthorization.policyAdmin",
    "roles/cloudkms.admin",
    "roles/cloudsql.admin",
    "roles/compute.networkAdmin",
    "roles/compute.securityAdmin",
    "roles/compute.xpnAdmin",
    "roles/container.admin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.roleAdmin",
    "roles/logging.configWriter",
    "roles/monitoring.admin",
    "roles/resourcemanager.folderAdmin",
    "roles/resourcemanager.projectCreator",
    "roles/resourcemanager.projectIamAdmin",
    "roles/secretmanager.admin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
  ])

  bindings = {
    for pair in setproduct(keys(var.environment_folder_ids), local.environment_apply_roles) :
    "${pair[0]}:${pair[1]}" => {
      environment = pair[0]
      role        = pair[1]
    }
  }
}

resource "google_folder_iam_member" "environment_apply" {
  for_each = local.bindings

  folder = var.environment_folder_ids[each.value.environment]
  role   = each.value.role
  member = "serviceAccount:${var.environment_apply_service_accounts[each.value.environment]}"
}

# Normal build/qualification/signing identities intentionally live outside Ring 0. Bootstrap
# owns only the exact capability providers; these service accounts are rebuildable normal-plane
# resources and no identity can impersonate another capability.
locals {
  supply_chain_identities = {
    canary               = { account = "arc-canary", capability = "canary" }
    builder              = { account = "artifact-builder", capability = "builder" }
    qualification_reader = { account = "artifact-qual-reader", capability = "qualification-reader" }
    qualifier            = { account = "artifact-qualifier", capability = "qualifier" }
    signer               = { account = "artifact-signer", capability = "signer" }
    promoter             = { account = "artifact-promoter", capability = "promoter" }
  }
  artifact_release_provider_ids = {
    canary               = "gh-arc-canary"
    builder              = "gh-arc-builder"
    qualification-reader = "gh-arc-qualification-reader"
    qualifier            = "gh-arc-qualifier"
    signer               = "gh-mindclade-internal-monorepo"
    promoter             = "gh-arc-promoter"
  }
  artifact_release_workflows = {
    canary               = "reusable-arc-wif-canary.yml"
    builder              = "reusable-arc-oci-build.yml"
    qualification-reader = "reusable-arc-oci-qualify.yml"
    qualifier            = "reusable-arc-qualification-attest.yml"
    signer               = "reusable-binauthz-sign.yml"
    promoter             = "reusable-gitops-promote.yml"
  }
  artifact_release_versions = {
    canary               = "v5.0.0"
    builder              = "v5.0.0"
    qualification-reader = "v5.0.0"
    qualifier            = "v5.0.0"
    signer               = "v5.0.0"
    promoter             = "v5.0.0"
  }
  artifact_release_subject_suffixes = {
    canary               = "ref:refs/heads/main"
    builder              = "ref:refs/heads/main"
    qualification-reader = "ref:refs/heads/main"
    qualifier            = "ref:refs/heads/main"
    signer               = "environment:release"
    promoter             = "environment:release"
  }
}

resource "google_service_account" "supply_chain" {
  for_each     = local.supply_chain_identities
  project      = var.ci_project_id
  account_id   = "sa-${each.value.account}"
  display_name = "Mindclade ${replace(each.value.account, "-", " ")}"
  description  = "Keyless ARC ${each.value.capability} identity; static keys are prohibited."
}

resource "google_service_account_iam_member" "supply_chain_github_wif" {
  for_each           = local.supply_chain_identities
  service_account_id = google_service_account.supply_chain[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = var.artifact_release_identities[each.value.capability].principal
}

resource "google_project_iam_member" "arc_builder_registry_writer" {
  project = var.ci_project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.supply_chain["builder"].email}"
}

resource "google_project_iam_member" "arc_qualification_registry_reader" {
  project = var.ci_project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.supply_chain["qualification_reader"].email}"
}

check "artifact_release_trust_contract" {
  assert {
    condition = alltrue([
      for capability, identity in var.artifact_release_identities :
      identity.workload_identity_provider == "${var.github_wif_pool_name}/providers/${local.artifact_release_provider_ids[capability]}" &&
      can(regex(
        "^repo:${var.github_org}@[0-9]+/mindclade-internal-monorepo@[0-9]+:${local.artifact_release_subject_suffixes[capability]}$",
        identity.subject,
      )) &&
      identity.principal == "principal://iam.googleapis.com/${var.github_wif_pool_name}/subject/${capability == "signer" ? "" : "arc-${capability}:"}${identity.subject}" &&
      identity.workflow_ref == "${var.github_org}/mindclade-internal-monorepo/.github/workflows/release.yml@refs/heads/main" &&
      identity.job_workflow_ref == "${var.github_org}/.github/.github/workflows/${local.artifact_release_workflows[capability]}@refs/tags/${local.artifact_release_versions[capability]}"
    ])
    error_message = "ARC release trust must match bootstrap's exact capability inventory, trusted-main caller, v4 execution workflows, and v5 promoter."
  }
}

resource "google_service_account" "arc_system_nodes" {
  project         = var.ci_project_id
  account_id      = "sa-arc-system-nodes"
  display_name    = "Mindclade ARC system nodes"
  description     = "Dedicated VM identity for the private ARC GKE system node pool."
  disabled        = false
  deletion_policy = "PREVENT"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_service_account" "dr_evidence_writer" {
  project         = var.ci_project_id
  account_id      = "sa-dr-evidence-writer"
  display_name    = "Mindclade DR evidence writer"
  description     = "Keyless create-only writer for protected scratch and staging DR evidence."
  disabled        = false
  deletion_policy = "PREVENT"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_service_account_iam_member" "dr_evidence_github_wif" {
  for_each = var.dr_evidence_identity.principals

  service_account_id = google_service_account.dr_evidence_writer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = each.value
}

locals {
  bazel_cache_accounts = {
    reader = {
      account_id   = "bazel-cache-reader"
      display_name = "Mindclade Bazel cache reader"
      description  = "Keyless read-only identity for pull-request Bazel cache access."
    }
    writer = {
      account_id   = "bazel-cache-writer"
      display_name = "Mindclade Bazel cache writer"
      description  = "Keyless create-only writer for trusted Bazel cache routes."
    }
  }
  bazel_cache_route_contract = {
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
  }
}

resource "google_service_account" "bazel_cache" {
  for_each = local.bazel_cache_accounts

  project         = var.ci_project_id
  account_id      = each.value.account_id
  display_name    = each.value.display_name
  description     = each.value.description
  disabled        = false
  deletion_policy = "PREVENT"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_service_account" "nix_cache_storage" {
  project         = var.ci_project_id
  account_id      = "nix-cache-storage"
  display_name    = "Mindclade Nix cache storage"
  description     = "Private Attic backend identity; HMAC creation and GitHub federation are intentionally out of scope."
  disabled        = false
  deletion_policy = "PREVENT"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_service_account" "workstation_image_publisher" {
  project         = var.ci_project_id
  account_id      = "workstation-image-pub"
  display_name    = "Mindclade workstation image publisher"
  description     = "Keyless create-only publisher for immutable NixOS raw-disk source objects."
  disabled        = false
  deletion_policy = "PREVENT"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_service_account_iam_member" "workstation_image_github_wif" {
  service_account_id = google_service_account.workstation_image_publisher.name
  role               = "roles/iam.workloadIdentityUser"
  member             = var.workstation_image_identity.principal
}

check "workstation_image_trust_contract" {
  assert {
    condition = (
      var.workstation_image_identity.workload_identity_provider == "${var.github_wif_pool_name}/providers/gh-workstation-image" &&
      var.workstation_image_identity.repository == "${var.github_org}/mindclade-internal-monorepo" &&
      var.workstation_image_identity.principal == "principal://iam.googleapis.com/${var.github_wif_pool_name}/subject/workstation-image:${var.workstation_image_identity.subject}" &&
      var.workstation_image_identity.workflow_ref == "${var.github_org}/mindclade-internal-monorepo/.github/workflows/nixos-image.yml@refs/heads/main" &&
      var.workstation_image_identity.job_workflow_ref == "${var.github_org}/.github/.github/workflows/reusable-nixos-gce-image-publish.yml@refs/tags/v5.0.0"
    )
    error_message = "Workstation image trust must remain isolated to bootstrap contract 2.0.0."
  }
}

resource "google_service_account_iam_member" "bazel_cache_github_wif" {
  for_each = var.bazel_cache_identity.routes

  service_account_id = google_service_account.bazel_cache[each.key == "pull-request-read" ? "reader" : "writer"].name
  role               = "roles/iam.workloadIdentityUser"
  member             = each.value.principal
}

check "bazel_cache_trust_contract" {
  assert {
    condition = (
      var.bazel_cache_identity.workload_identity_provider == "${var.github_wif_pool_name}/providers/gh-bazel-cache" &&
      var.bazel_cache_identity.repository == "${var.github_org}/mindclade-internal-monorepo" &&
      can(regex("^[0-9]+$", var.bazel_cache_identity.repository_owner_id)) &&
      can(regex("^[0-9]+$", var.bazel_cache_identity.repository_id)) &&
      alltrue([
        for route, expected in local.bazel_cache_route_contract :
        var.bazel_cache_identity.routes[route].access == expected.access &&
        var.bazel_cache_identity.routes[route].event_name == expected.event_name &&
        var.bazel_cache_identity.routes[route].ref_policy == expected.ref_policy &&
        var.bazel_cache_identity.routes[route].workflow_path == expected.workflow_path &&
        var.bazel_cache_identity.routes[route].principal == "principal://iam.googleapis.com/${var.github_wif_pool_name}/subject/bazel-cache:${route}"
      ])
    )
    error_message = "Bazel cache trust must match bootstrap contract 2.0.0 with pull-request read and exact trusted write routes."
  }
}

resource "google_project_iam_member" "arc_system_nodes" {
  for_each = toset(["roles/container.defaultNodeServiceAccount"])
  project  = var.ci_project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.arc_system_nodes.email}"
}
