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
    project_ids = { ci = "mc-common-ci" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "development" {
  config_path = "../../../2-environments/development/shared-projects"
  mock_outputs = {
    project_numbers = { platform = "100000000001" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../1-org/kms"
  mock_outputs = {
    crypto_key_ids = {
      ci_artifacts = "projects/mock/locations/us-central1/keyRings/mock-global/cryptoKeys/ci-artifacts"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "access_logs" {
  config_path = "../../shared/workstation-image-access-logs"
  mock_outputs = {
    bucket = { name = "mc-workstation-image-access-logs" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "automation" {
  config_path = "../../../1-org/automation-iam"
  mock_outputs = {
    workstation_image_publisher_service_account = "workstation-image-pub@mc-common-ci.iam.gserviceaccount.com"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals { module_version = "v0.4.0" }

terraform {
  source = "${include.root.locals.module_source_base}//storage?ref=${local.module_version}"
}

inputs = {
  project_id                  = dependency.common_projects.outputs.project_ids["ci"]
  name                        = "${include.root.locals.prefix}-common-ci-workstation-images"
  location                    = include.root.locals.region
  storage_class               = "STANDARD"
  environment                 = "ci"
  owner                       = "developer-platform"
  data_classification         = "internal"
  kms_key_name                = dependency.kms.outputs.crypto_key_ids["ci_artifacts"]
  access_log_bucket           = dependency.access_logs.outputs.bucket.name
  access_log_object_prefix    = "workstation-images/common-ci/"
  versioning_enabled          = true
  create_only_workload        = true
  soft_delete_retention_days  = 30
  retention_period_seconds    = 31536000
  lock_retention_policy       = true
  retention_lock_confirmation = "LOCKING A CLOUD STORAGE RETENTION POLICY IS IRREVERSIBLE"
  lifecycle_rules = [{
    action        = "AbortIncompleteMultipartUpload"
    age_days      = 7
    storage_class = null
    with_state    = null
  }]
  object_viewers = [
    "serviceAccount:${dependency.automation.outputs.workstation_image_publisher_service_account}",
    "serviceAccount:service-${dependency.development.outputs.project_numbers["platform"]}@compute-system.iam.gserviceaccount.com",
  ]
  object_creators = [
    "serviceAccount:${dependency.automation.outputs.workstation_image_publisher_service_account}",
  ]
  labels = merge(include.root.locals.common_labels, {
    authority = "github-actions"
    workload  = "workstation-image-source"
  })
}
