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
    crypto_key_ids = { dr-evidence = "projects/mock/locations/us/keyRings/mock/cryptoKeys/dr-evidence" }
  }
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
  name                        = "${include.root.locals.prefix}-dr-evidence-access-logs"
  location                    = "US"
  storage_class               = "STANDARD"
  environment                 = "global"
  owner                       = "security"
  data_classification         = "restricted"
  kms_key_name                = dependency.kms.outputs.crypto_key_ids["dr-evidence"]
  access_log_bucket           = null
  versioning_enabled          = true
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
  object_creators = ["group:cloud-storage-analytics@google.com"]
  labels = merge(include.root.locals.common_labels, {
    purpose = "dr-evidence-access-logs"
  })
}
