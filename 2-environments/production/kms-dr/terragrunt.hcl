# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# U.S. recovery-region CMEK. Key placement is immutable, so DR keys have an independent
# state unit and are never added to the primary us-central1 ring.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//kms?ref=${local.module_version}"
}

locals {
  module_version = "v0.4.0"
}

dependency "shared" {
  config_path = "../shared-projects"

  mock_outputs = {
    project_numbers = { platform = "100000000003" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id    = include.root.locals.seed_project_id
  location      = include.root.locals.dr_region
  key_ring_name = "${include.root.locals.prefix}-production-dr"

  keys = {
    artifacts = { rotation_period_seconds = 7776000, protection_level = "HSM" }
    secrets   = { rotation_period_seconds = 7776000, protection_level = "HSM" }
    sql       = { rotation_period_seconds = 7776000, protection_level = "HSM" }
    storage   = { rotation_period_seconds = 7776000, protection_level = "HSM" }
  }

  encrypter_decrypters = {
    secrets = ["serviceAccount:service-${dependency.shared.outputs.project_numbers["platform"]}@gcp-sa-secretmanager.iam.gserviceaccount.com"]
    sql     = ["serviceAccount:service-${dependency.shared.outputs.project_numbers["platform"]}@gcp-sa-cloud-sql.iam.gserviceaccount.com"]
    storage = [
      "serviceAccount:service-${dependency.shared.outputs.project_numbers["platform"]}@gcp-sa-gkebackup.iam.gserviceaccount.com",
      "serviceAccount:service-${dependency.shared.outputs.project_numbers["platform"]}@gs-project-accounts.iam.gserviceaccount.com",
    ]
  }

  labels = merge(include.root.locals.common_labels, { purpose = "us-dr" })
}
