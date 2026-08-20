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
      identity.job_workflow_ref == "${var.github_org}/.github/.github/workflows/${local.artifact_release_workflows[capability]}@refs/tags/v4.0.0"
    ])
    error_message = "ARC release trust must match bootstrap's exact capability inventory, trusted-main caller, and immutable v4 reusable workflows."
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

resource "google_project_iam_member" "arc_system_nodes" {
  for_each = toset(["roles/container.defaultNodeServiceAccount"])
  project  = var.ci_project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.arc_system_nodes.email}"
}
