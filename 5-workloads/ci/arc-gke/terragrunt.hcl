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

dependency "arc_vpc" {
  config_path = "../../../3-networks/ci/arc-vpc"
  mock_outputs = {
    network_self_link    = { arc = "projects/mc-common-ci/global/networks/mc-ci-arc-vpc" }
    subnetwork_names     = { arc = "arc-nodes" }
    pods_range_names     = { arc = "arc-pods" }
    services_range_names = { arc = "arc-services" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "automation" {
  config_path = "../../../1-org/automation-iam"
  mock_outputs = {
    arc_system_node_service_account = "sa-arc-system-nodes@mc-common-ci.iam.gserviceaccount.com"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  module_version = "v0.4.0"
}

terraform {
  source = "${include.root.locals.module_source_base}//gke?ref=${local.module_version}"
}

inputs = {
  project_id = dependency.common_projects.outputs.project_ids["ci"]
  name       = "${include.root.locals.prefix}-ci-arc"
  region     = include.root.locals.region

  network                      = dependency.arc_vpc.outputs.network_self_link["arc"]
  subnetwork                   = dependency.arc_vpc.outputs.subnetwork_names["arc"]
  pod_secondary_range_name     = dependency.arc_vpc.outputs.pods_range_names["arc"]
  service_secondary_range_name = dependency.arc_vpc.outputs.services_range_names["arc"]
  master_ipv4_cidr_block       = "10.243.0.0/28"
  master_authorized_networks = [{
    cidr_block   = "10.240.0.0/20"
    display_name = "arc-private-nodes"
  }]

  system_node_service_account_email = dependency.automation.outputs.arc_system_node_service_account
  rbac_security_group               = "gke-security-groups@${include.root.locals.domain}"
  environment                       = "ci"
  owner                             = "platform"
  data_classification               = "internal"
  resource_labels = {
    authority = "artifact-release"
    isolation = "dedicated-vpc"
  }

  release_channel                    = "REGULAR"
  kubernetes_version                 = "1.36.2-gke.2064000"
  enable_gcs_fuse_csi_driver         = false
  enable_backup_agent                = false
  enable_secret_sync                 = true
  secret_sync_rotation_interval      = "120s"
  database_encryption_key_name       = null
  system_node_pool_machine_type      = "n2-standard-8"
  system_node_pool_total_min_nodes   = 3
  system_node_pool_total_max_nodes   = 9
  system_node_pool_max_pods_per_node = 64
  system_node_pool_boot_disk_size_gb = 100
}
