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
  config_path = "../../shared/bazel-cache-access-logs"
  mock_outputs = {
    bucket = { name = "mc-bazel-cache-access-logs" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "automation" {
  config_path = "../../../1-org/automation-iam"
  mock_outputs = {
    bazel_cache_service_accounts = {
      reader = "bazel-cache-reader@mc-common-ci.iam.gserviceaccount.com"
      writer = "bazel-cache-writer@mc-common-ci.iam.gserviceaccount.com"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  module_version = "v0.4.0"
}

terraform {
  source = "${include.root.locals.module_source_base}//bazel_remote_cache?ref=${local.module_version}"
}

inputs = {
  project_id               = dependency.common_projects.outputs.project_ids["ci"]
  bucket_name              = "${include.root.locals.prefix}-common-ci-bazel-cache"
  location                 = include.root.locals.region
  kms_key_name             = dependency.kms.outputs.crypto_key_ids["ci_artifacts"]
  access_log_bucket        = dependency.access_logs.outputs.bucket.name
  access_log_object_prefix = "bazel-remote-cache/common-ci/"
  environment              = "ci"
  owner                    = "developer-platform"
  data_classification      = "internal"
  reader_members = [
    "serviceAccount:${dependency.automation.outputs.bazel_cache_service_accounts.reader}",
  ]
  writer_members = [
    "serviceAccount:${dependency.automation.outputs.bazel_cache_service_accounts.writer}",
  ]
  cache_ttl_days              = 30
  noncurrent_version_ttl_days = 1
  soft_delete_retention_days  = 7
  retention_period_seconds    = 86400
  labels = merge(include.root.locals.common_labels, {
    authority = "github-actions"
    workload  = "bazel-remote-cache"
  })
}
