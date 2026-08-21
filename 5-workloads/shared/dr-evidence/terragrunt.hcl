# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "common_projects" {
  config_path                             = "../../../1-org/common-projects"
  mock_outputs                            = { project_ids = { security = "mc-common-security", ci = "mc-common-ci" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../1-org/kms-dr-evidence"
  mock_outputs = {
    crypto_key_ids = { dr-evidence = "projects/mock/locations/us/keyRings/mock/cryptoKeys/dr-evidence" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "automation" {
  config_path = "../../../1-org/automation-iam"
  mock_outputs = {
    dr_evidence_identity_contract = {
      WIF_PROVIDER_DR_EVIDENCE = "projects/000000000001/locations/global/workloadIdentityPools/github/providers/gh-dr-evidence"
      SA_DR_EVIDENCE_WRITER    = "sa-dr-evidence-writer@mc-common-ci.iam.gserviceaccount.com"
      principals               = {}
      job_workflow_ref         = "mindclade/.github/.github/workflows/reusable-dr-evidence.yml@refs/tags/v4.0.0"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "access_logs" {
  config_path                             = "../dr-evidence-access-logs"
  mock_outputs                            = { bucket = { name = "mc-dr-evidence-access-logs" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  module_version = "v0.4.0"
}

terraform {
  source = "${include.root.locals.module_source_base}//storage?ref=${local.module_version}"
}

inputs = {
  project_id                  = dependency.common_projects.outputs.project_ids["security"]
  name                        = "${include.root.locals.prefix}-dr-evidence"
  location                    = "US"
  storage_class               = "STANDARD"
  environment                 = "global"
  owner                       = "security"
  data_classification         = "restricted"
  kms_key_name                = dependency.kms.outputs.crypto_key_ids["dr-evidence"]
  access_log_bucket           = dependency.access_logs.outputs.bucket.name
  access_log_object_prefix    = "dr-evidence/"
  versioning_enabled          = true
  create_only_workload        = true
  soft_delete_retention_days  = 90
  retention_period_seconds    = 220752000
  lock_retention_policy       = true
  retention_lock_confirmation = "LOCKING A CLOUD STORAGE RETENTION POLICY IS IRREVERSIBLE"
  lifecycle_rules = [{
    action        = "AbortIncompleteMultipartUpload"
    age_days      = 7
    storage_class = null
    with_state    = null
  }]
  # Terragrunt evaluates `locals` before it resolves `dependency` blocks, so the writer member is
  # built here rather than hoisted into a local — a local that references a dependency output
  # fails HCL evaluation outright with "dependency is not defined".
  object_creators = ["serviceAccount:${dependency.automation.outputs.dr_evidence_identity_contract.SA_DR_EVIDENCE_WRITER}"]
  object_viewers  = ["serviceAccount:${dependency.automation.outputs.dr_evidence_identity_contract.SA_DR_EVIDENCE_WRITER}"]
  labels = merge(include.root.locals.common_labels, {
    purpose = "dr-evidence"
  })
}
