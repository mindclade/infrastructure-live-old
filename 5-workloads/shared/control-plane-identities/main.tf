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
    "roles/binaryauthorization.attestorsVerifier",
    "roles/binaryauthorization.policyViewer",
    "roles/containeranalysis.occurrences.viewer",
  ])

  verifier_project_bindings = {
    for pair in setproduct(toset(values(var.platform_project_ids)), local.verifier_roles) :
    "${pair[0]}:${pair[1]}" => { project = pair[0], role = pair[1] }
  }

  # Production only. `staging` was here, and its presence defeated the control this key exists
  # to provide: roles/cloudkms.signer on `production-eligibility-decisions` let the staging
  # control-plane-admin mint decisions for production.
  #
  # Nothing downstream can tell the difference. The decision schema carries digests, an epoch, a
  # result and timestamps -- no issuer and no environment -- and verify_response checks only the
  # key id and key version. A staging-signed decision over a production bundle digest is
  # therefore cryptographically indistinguishable from a production-issued one, which is the
  # whole premise of the protected-eligibility flow.
  #
  # If staging must rehearse the flow, it needs its OWN key ring entry, not shared use of this
  # one; the alternative -- an issuer field with a per-environment allowlist in verify_response --
  # is a schema change across gitops and .github rather than a binding change here.
  eligibility_admin_principals = {
    for environment in ["production"] : environment =>
    "principal://iam.googleapis.com/projects/${var.platform_project_numbers[environment]}/locations/global/workloadIdentityPools/${var.platform_project_ids[environment]}.svc.id.goog/subject/ns/mindclade-system/sa/control-plane-admin"
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

resource "google_service_account" "production_qualification" {
  for_each = {
    evaluator = "Submits qualified evidence and verifies signed production-eligibility decisions through IAP."
    reader    = "Reads the dedicated GitHub App key for exact-source qualification."
    writer    = "Publishes immutable production qualification evidence to the protected archive."
  }

  project      = var.security_project_id
  account_id   = "sa-prod-qual-${each.key}"
  display_name = "Production qualification ${each.key}"
  description  = each.value
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

resource "google_service_account_iam_member" "production_qualification_wif" {
  for_each = google_service_account.production_qualification

  service_account_id = each.value.name
  role               = "roles/iam.workloadIdentityUser"
  member             = var.production_qualification_identity.principal
}

resource "google_service_account_iam_member" "production_qualification_evaluator_sign_jwt" {
  service_account_id = google_service_account.production_qualification["evaluator"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = var.production_qualification_identity.principal
}

resource "google_project_iam_member" "production_qualification_evaluator_iap" {
  for_each = {
    staging    = var.platform_project_ids.staging
    production = var.platform_project_ids.production
  }

  project = each.value
  role    = "roles/iap.httpsResourceAccessor"
  member  = "serviceAccount:${google_service_account.production_qualification["evaluator"].email}"
}

resource "google_kms_crypto_key" "production_eligibility" {
  name                          = "production-eligibility-decisions"
  key_ring                      = var.eligibility_signing_key_ring_id
  purpose                       = "ASYMMETRIC_SIGN"
  skip_initial_version_creation = true

  version_template {
    algorithm        = "EC_SIGN_ED25519"
    protection_level = "HSM"
  }

  labels = {
    managed_by  = "terraform"
    repository  = "infrastructure-live"
    purpose     = "production-eligibility"
    criticality = "critical"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key_version" "production_eligibility" {
  crypto_key = google_kms_crypto_key.production_eligibility.id

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key_iam_member" "production_eligibility_signer" {
  for_each = local.eligibility_admin_principals

  crypto_key_id = google_kms_crypto_key.production_eligibility.id
  role          = "roles/cloudkms.signer"
  member        = each.value
}

resource "google_kms_crypto_key_iam_member" "production_eligibility_public_key" {
  for_each = toset(["evaluator", "writer"])

  crypto_key_id = google_kms_crypto_key.production_eligibility.id
  role          = "roles/cloudkms.publicKeyViewer"
  member        = "serviceAccount:${google_service_account.production_qualification[each.value].email}"
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

resource "google_secret_manager_secret" "github_app_production_qualification_pem" {
  project   = var.security_project_id
  secret_id = "github-app-production-qualification-reader-pem"

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
    purpose     = "production-qualification-source-read"
    criticality = "critical"
  }

  depends_on = [google_kms_crypto_key_iam_member.secret_manager]
}

resource "google_secret_manager_secret_iam_member" "production_qualification_reader" {
  project   = var.security_project_id
  secret_id = google_secret_manager_secret.github_app_production_qualification_pem.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.production_qualification["reader"].email}"
}

resource "google_secret_manager_secret" "github_app_arc_pem" {
  project   = var.security_project_id
  secret_id = "github-app-arc-pem"

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
    purpose     = "arc-runner-registration"
    criticality = "critical"
  }

  depends_on = [google_kms_crypto_key_iam_member.secret_manager]
}

resource "google_secret_manager_secret" "github_app_arc_id" {
  project   = var.security_project_id
  secret_id = "github-app-arc-id"

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
    purpose     = "arc-runner-registration"
    criticality = "critical"
  }

  depends_on = [google_kms_crypto_key_iam_member.secret_manager]
}

resource "google_secret_manager_secret" "github_app_arc_installation_id" {
  project   = var.security_project_id
  secret_id = "github-app-arc-installation-id"

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
    purpose     = "arc-runner-registration"
    criticality = "critical"
  }

  depends_on = [google_kms_crypto_key_iam_member.secret_manager]
}

locals {
  arc_secret_sync_principals = toset([
    for namespace in ["arc-build", "arc-canary", "arc-qualify"] :
    "principal://iam.googleapis.com/projects/${var.ci_project_number}/locations/global/workloadIdentityPools/${var.ci_project_id}.svc.id.goog/subject/ns/${namespace}/sa/arc-secret-sync"
  ])

  arc_secret_sync_bindings = {
    for pair in setproduct(
      toset([
        google_secret_manager_secret.github_app_arc_id.secret_id,
        google_secret_manager_secret.github_app_arc_installation_id.secret_id,
        google_secret_manager_secret.github_app_arc_pem.secret_id,
      ]),
      local.arc_secret_sync_principals,
      ) : "${pair[0]}:${pair[1]}" => {
      secret_id = pair[0]
      member    = pair[1]
    }
  }
}

resource "google_secret_manager_secret_iam_member" "arc_secret_sync" {
  for_each = local.arc_secret_sync_bindings

  project   = var.security_project_id
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}

resource "google_secret_manager_secret" "github_app_promoter_pem" {
  project   = var.security_project_id
  secret_id = "github-app-promoter-pem"

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
    purpose     = "gitops-promotion"
    criticality = "critical"
  }

  depends_on = [google_kms_crypto_key_iam_member.secret_manager]
}

resource "google_secret_manager_secret_iam_member" "arc_promoter" {
  project   = var.security_project_id
  secret_id = google_secret_manager_secret.github_app_promoter_pem.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.arc_promoter_service_account_email}"
}

resource "google_project_iam_member" "gitops_verifier" {
  for_each = local.verifier_project_bindings

  project = each.value.project
  role    = each.value.role
  member  = "serviceAccount:${google_service_account.gitops_verifier.email}"
}
