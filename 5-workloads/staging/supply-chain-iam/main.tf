# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

locals {
  member = { for k, v in var.service_accounts : k => "serviceAccount:${v}" }
  # Notes Attacher and KMS Signer/Verifier remain scoped per attestor/key in the Binary
  # Authorization module. The custom project role deliberately omits occurrence delete and
  # update, while note-scoped attachment prevents one issuer from forging another stage.
  attestation_issuers = {
    builder   = local.member.builder
    qualifier = local.member.qualifier
    signer    = local.member.signer
  }
}

resource "google_project_iam_member" "builder_writer" {
  count   = var.environment == "development" ? 1 : 0
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = local.member.builder
}
resource "google_project_iam_member" "qualifier_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = local.member.qualifier
}
resource "google_project_iam_member" "qualifier_analysis" {
  project = var.project_id
  role    = "roles/containeranalysis.occurrences.viewer"
  member  = local.member.qualifier
}
resource "google_project_iam_member" "signer_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = local.member.signer
}

# Every issuer can address attestors and occurrences in each rehearsal environment. The
# Binary Authorization module is the enforcement boundary: it grants each identity Notes
# Attacher and KMS Signer/Verifier only for that identity's own attestor/key. Google's
# attestation API also requires occurrence creation on the project that stores the occurrence.
resource "google_project_iam_custom_role" "attestation_occurrence_creator" {
  project     = var.project_id
  role_id     = "mindcladeAttestationOccurrenceCreator"
  title       = "Mindclade attestation occurrence creator"
  description = "Create and verify attestation occurrences without update or deletion authority."
  permissions = [
    "containeranalysis.occurrences.create",
    "containeranalysis.occurrences.get",
    "containeranalysis.occurrences.list",
    "resourcemanager.projects.get",
    "resourcemanager.projects.list",
  ]
}

resource "google_project_iam_member" "attestation_issuer_viewer" {
  for_each = local.attestation_issuers
  project  = var.project_id
  role     = "roles/binaryauthorization.attestorsViewer"
  member   = each.value
}

resource "google_project_iam_member" "attestation_issuer_occurrence_creator" {
  for_each = local.attestation_issuers
  project  = var.project_id
  role     = google_project_iam_custom_role.attestation_occurrence_creator.name
  member   = each.value
}
resource "google_project_iam_member" "promoter_reader" {
  count   = var.environment == "development" ? 1 : 0
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = local.member.promoter
}
resource "google_project_iam_member" "promoter_writer" {
  count   = var.environment == "development" ? 0 : 1
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = local.member.promoter
}
