# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

locals {
  root         = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  environment    = local.env_vars.locals.environment
  module_version = "v0.4.0"
  node_locations = {
    development = ["us-central1-a", "us-central1-b"]
    staging     = ["us-central1-a", "us-central1-b"]
    production  = ["us-central1-a", "us-central1-b", "us-central1-c"]
  }
}

terraform {
  source = "${local.root.locals.module_source_base}//bazel_remote_execution?ref=${local.module_version}"
}

dependency "gke" {
  config_path = "${get_repo_root()}/5-workloads/${local.environment}/gke"
  mock_outputs = {
    cluster_name     = "mc-${local.environment}"
    cluster_location = local.account_vars.locals.region
    project_id       = "mc-${local.environment}-platform"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "vpc" {
  config_path = "${get_repo_root()}/3-networks/${local.environment}/shared-vpc-host"
  mock_outputs = {
    pods_range_names = { (local.environment) = "mc-${local.environment}-pods" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "cache" {
  config_path = "${get_repo_root()}/5-workloads/${local.environment}/bazel-remote-cache"
  mock_outputs = {
    bucket = { name = "mc-${local.environment}-bazel-cache" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id                  = dependency.gke.outputs.project_id
  cluster_name                = dependency.gke.outputs.cluster_name
  region                      = dependency.gke.outputs.cluster_location
  node_locations              = local.node_locations[local.environment]
  pod_secondary_range_name    = dependency.vpc.outputs.pods_range_names[local.environment]
  node_service_account_id     = "bazel-executor-nodes"
  executor_service_account_id = "bazel-remote-executor"
  kubernetes_namespace        = "mindclade-build"
  kubernetes_service_account  = "bazel-remote-executor"
  executor_image              = "${local.account_vars.locals.region}-docker.pkg.dev/${dependency.gke.outputs.project_id}/workers/buildfarm-worker@sha256:7a10e8f37daecf2e8485acf872e00b02ec6fb7519fe4b6fc32e71ce2b033747d"
  cache_bucket_name           = dependency.cache.outputs.bucket.name
  environment                 = local.environment
  owner                       = "developer-platform"
  profile                     = local.environment == "production" ? "HIGH_MEMORY" : "GENERAL_PURPOSE"
  capacity_type               = "ON_DEMAND"
  total_min_nodes             = local.environment == "development" ? 0 : 2
  total_max_nodes             = local.environment == "production" ? 40 : 12
  max_pods_per_node           = 32
  resource_labels = merge(local.root.locals.common_labels, {
    authority = "terraform"
    workload  = "bazel-remote-execution"
  })
}
