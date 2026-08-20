# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
locals { member = { for k, v in var.service_accounts : k => "serviceAccount:${v}" } }

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
