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
    project_ids     = { ci = "mc-common-ci" }
    project_numbers = { ci = "000000000001" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../1-org/kms"
  mock_outputs = {
    crypto_key_ids = {
      ci_secrets = "projects/mock/locations/us-central1/keyRings/mock-global/cryptoKeys/ci-secrets"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  module_version = "v0.4.0"
}

terraform {
  source = "${include.root.locals.module_source_base}//secret_manager?ref=${local.module_version}"
}

inputs = {
  project_id          = dependency.common_projects.outputs.project_ids["ci"]
  project_number      = dependency.common_projects.outputs.project_numbers["ci"]
  environment         = "ci"
  owner               = "developer-platform"
  data_classification = "restricted"

  replication = {
    user_managed = [{
      location     = include.root.locals.region
      kms_key_name = dependency.kms.outputs.crypto_key_ids["ci_secrets"]
    }]
  }

  workload_identity_bindings = {
    attic-secret-sync = {
      namespace       = "mindclade-cache"
      service_account = "attic-secret-sync"
    }
  }

  secrets = {
    attic-token-rs256-private-key = {
      description = "Attic server JWT signing and verification key; never exposed to cache clients."
      accessors   = ["attic-secret-sync"]
      annotations = { "rotation-policy" = "protected-out-of-band" }
    }
    attic-database-url = {
      description = "Attic PostgreSQL connection URL for the qualified private service."
      accessors   = ["attic-secret-sync"]
      annotations = { "rotation-policy" = "protected-out-of-band" }
    }
    attic-gcs-hmac-access-key-id = {
      description = "GCS XML API HMAC access-key ID owned by the dedicated Nix cache storage service account."
      accessors   = ["attic-secret-sync"]
      annotations = { "rotation-policy" = "paired-protected-out-of-band" }
    }
    attic-gcs-hmac-secret-access-key = {
      description = "GCS XML API HMAC secret access key; generated and written without Terraform state."
      accessors   = ["attic-secret-sync"]
      annotations = { "rotation-policy" = "paired-protected-out-of-band" }
    }
  }

  alert_on_unexpected_access = true
  labels = merge(include.root.locals.common_labels, {
    workload = "nix-binary-cache"
  })
}
