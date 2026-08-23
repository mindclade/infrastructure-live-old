# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "common_projects" {
  config_path = "../../../1-org/common-projects"
  mock_outputs = {
    project_ids = { logging = "mc-common-logging" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../1-org/kms"
  mock_outputs = {
    crypto_key_ids = {
      logs = "projects/mock/locations/us-central1/keyRings/mock-global/cryptoKeys/logs"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals { module_version = "v0.4.0" }

terraform {
  source = "${include.root.locals.module_source_base}//storage?ref=${local.module_version}"
}

inputs = {
  project_id                  = dependency.common_projects.outputs.project_ids["logging"]
  name                        = "${include.root.locals.prefix}-workstation-image-access-logs"
  location                    = include.root.locals.region
  storage_class               = "STANDARD"
  environment                 = "global"
  owner                       = "developer-platform"
  data_classification         = "restricted"
  kms_key_name                = dependency.kms.outputs.crypto_key_ids["logs"]
  access_log_bucket           = null
  versioning_enabled          = true
  soft_delete_retention_days  = 30
  retention_period_seconds    = 34560000
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
    purpose = "workstation-image-access-logs"
  })
}
