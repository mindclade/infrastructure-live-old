# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
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

# Normal build/qualification/signing identities intentionally live outside Ring 0. The
# Buildkite provider is bootstrap-owned, but the capabilities it can impersonate are normal
# platform resources and can be rebuilt after bootstrap recovery.
locals {
  supply_chain_identities = {
    builder   = { account = "artifact-builder",   step = "artifact-build" }
    qualifier = { account = "artifact-qualifier", step = "artifact-qualify" }
    signer    = { account = "artifact-signer",    step = "artifact-sign" }
    promoter  = { account = "artifact-promoter",  step = "artifact-promote" }
  }
  buildkite_step_principals = {
    for name, cfg in local.supply_chain_identities : name =>
    "principalSet://iam.googleapis.com/${var.buildkite_wif_pool_name}/attribute.step_key/${cfg.step}"
  }
}

resource "google_service_account" "supply_chain" {
  for_each = local.supply_chain_identities
  project      = var.ci_project_id
  account_id   = "sa-${each.value.account}"
  display_name = "Mindclade ${replace(each.value.account, "-", " ")}"
  description  = "Keyless Buildkite identity for ${each.value.step}; static keys are prohibited."
}

resource "google_service_account_iam_member" "supply_chain_wif" {
  for_each = local.supply_chain_identities
  service_account_id = google_service_account.supply_chain[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.buildkite_step_principals[each.key]
}
