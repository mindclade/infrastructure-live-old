# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "common_projects" {
  config_path                             = "../../../1-org/common-projects"
  mock_outputs                            = { project_ids = { security = "mc-common-security" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../1-org/kms-dr-evidence"
  mock_outputs = {
    crypto_key_ids = {
      production-qualification-evidence = "projects/mock/locations/us/keyRings/mock/cryptoKeys/production-qualification-evidence"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "identities" {
  config_path = "../control-plane-identities"
  mock_outputs = {
    service_accounts = {
      production_qualification_writer = "sa-prod-qual-writer@mc-common-security.iam.gserviceaccount.com"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "access_logs" {
  config_path                             = "../production-qualification-access-logs"
  mock_outputs                            = { bucket = { name = "mc-production-qualification-access-logs" } }
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
  name                        = "${include.root.locals.prefix}-production-qualification-evidence"
  location                    = "US"
  storage_class               = "STANDARD"
  environment                 = "global"
  owner                       = "security"
  data_classification         = "restricted"
  kms_key_name                = dependency.kms.outputs.crypto_key_ids["production-qualification-evidence"]
  access_log_bucket           = dependency.access_logs.outputs.bucket.name
  access_log_object_prefix    = "production-qualification/"
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
  object_creators = ["serviceAccount:${dependency.identities.outputs.service_accounts["production_qualification_writer"]}"]
  object_viewers  = ["serviceAccount:${dependency.identities.outputs.service_accounts["production_qualification_writer"]}"]
  labels = merge(include.root.locals.common_labels, {
    purpose = "production-qualification-evidence"
  })
}
