# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Source publication is deliberately external evidence. Protected CI injects the four outputs
# from the exact `nixos-image.yml` run; absent, malformed, mutable, or cross-bucket values fail
# before a plan can create a Compute Image.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "shared" {
  config_path = "../../../2-environments/development/shared-projects"
  mock_outputs = {
    project_ids     = { platform = "mc-development-platform" }
    project_numbers = { platform = "100000000001" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../2-environments/development/kms"
  mock_outputs = {
    crypto_key_ids = {
      workstation = "projects/mc-bootstrap-seed/locations/us-central1/keyRings/mc-development/cryptoKeys/workstation"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "source" {
  config_path = "../../ci/workstation-image-source"
  mock_outputs = {
    bucket = { name = "mc-common-ci-workstation-images" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  module_version           = "v0.4.0"
  source_uri               = include.root.locals.account_vars.locals.workstation_image_source_uri
  source_object_generation = include.root.locals.account_vars.locals.workstation_image_source_object_generation
  source_sha256            = include.root.locals.account_vars.locals.workstation_image_source_sha256
  image_contract_sha256    = include.root.locals.account_vars.locals.workstation_image_contract_sha256
}

terraform {
  source = "${include.root.locals.module_source_base}//compute_image?ref=${local.module_version}"
}

inputs = {
  project_id                    = dependency.shared.outputs.project_ids["platform"]
  qualification_state           = include.root.locals.account_vars.locals.workstation_image_source_state
  name                          = "${include.root.locals.prefix}-development-workstation-${substr(local.source_sha256, 0, 12)}"
  source_uri                    = local.source_uri
  source_bucket_name            = dependency.source.outputs.bucket.name
  source_object_generation      = local.source_object_generation
  source_sha256                 = local.source_sha256
  image_contract_sha256         = local.image_contract_sha256
  kms_key_name                  = dependency.kms.outputs.crypto_key_ids["workstation"]
  compute_service_account_email = "service-${dependency.shared.outputs.project_numbers["platform"]}@compute-system.iam.gserviceaccount.com"
  environment                   = "development"
  owner                         = "developer-platform"
  data_classification           = "internal"
  labels = merge(include.root.locals.common_labels, {
    authority = "terraform"
    workload  = "developer-workstation"
  })
}
