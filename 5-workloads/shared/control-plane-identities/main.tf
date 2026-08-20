# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

locals {
  # These are repository-local direct workflows, so workflow_ref is the immutable claim to
  # authorize. job_workflow_ref exists only for jobs executing inside reusable workflows.
  gitops_workflow_principals = {
    render   = "principalSet://iam.googleapis.com/${var.github_wif_pool_name}/attribute.workflow_ref/${var.github_org}/gitops/.github/workflows/render.yml@refs/heads/main"
    verifier = "principalSet://iam.googleapis.com/${var.github_wif_pool_name}/attribute.workflow_ref/${var.github_org}/gitops/.github/workflows/provenance.yml@refs/heads/main"
  }

  verifier_roles = toset([
    "roles/artifactregistry.reader",
    "roles/binaryauthorization.attestorsViewer",
    "roles/containeranalysis.occurrences.viewer",
  ])

  verifier_project_bindings = {
    for pair in setproduct(toset(values(var.platform_project_ids)), local.verifier_roles) :
    "${pair[0]}:${pair[1]}" => { project = pair[0], role = pair[1] }
  }
}

resource "google_service_account" "gitops_render" {
  project      = var.security_project_id
  account_id   = "sa-gitops-render"
  display_name = "GitOps deterministic render"
  description  = "Reads only the GitHub App key used to render immutable monorepo releases."
}

resource "google_service_account" "gitops_verifier" {
  project      = var.security_project_id
  account_id   = "sa-gitops-verifier"
  display_name = "GitOps artifact verifier"
  description  = "Read-only verification of Artifact Registry images and Binary Authorization attestations."
}

resource "google_service_account_iam_member" "gitops_wif" {
  for_each = {
    render   = google_service_account.gitops_render.name
    verifier = google_service_account.gitops_verifier.name
  }

  service_account_id = each.value
  role               = "roles/iam.workloadIdentityUser"
  member             = local.gitops_workflow_principals[each.key]
}

resource "google_project_service_identity" "secret_manager" {
  provider = google-beta
  project  = var.security_project_id
  service  = "secretmanager.googleapis.com"
}

resource "google_kms_crypto_key_iam_member" "secret_manager" {
  crypto_key_id = var.secret_kms_key_id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_project_service_identity.secret_manager.email}"
}

# Only the normal-runtime GitOps render credential lives here. The private Terraform
# module-reader secret is a Ring-0 prerequisite owned by bootstrap so infrastructure-live
# can initialize from a clean organization.
resource "google_secret_manager_secret" "github_app_render_pem" {
  project   = var.security_project_id
  secret_id = "github-app-render-pem"

  replication {
    user_managed {
      replicas {
        location = var.region

        customer_managed_encryption {
          kms_key_name = var.secret_kms_key_id
        }
      }
    }
  }

  labels = {
    managed_by  = "terraform"
    repository  = "infrastructure-live"
    purpose     = "gitops-render"
    criticality = "critical"
  }

  depends_on = [google_kms_crypto_key_iam_member.secret_manager]
}

resource "google_secret_manager_secret_iam_member" "gitops_render" {
  project   = var.security_project_id
  secret_id = google_secret_manager_secret.github_app_render_pem.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.gitops_render.email}"
}

resource "google_project_iam_member" "gitops_verifier" {
  for_each = local.verifier_project_bindings

  project = each.value.project
  role    = each.value.role
  member  = "serviceAccount:${google_service_account.gitops_verifier.email}"
}
