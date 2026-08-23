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

  release_channel               = "REGULAR"
  kubernetes_version            = "1.36.2-gke.2064000"
  enable_gcs_fuse_csi_driver    = false
  enable_backup_agent           = false
  enable_secret_sync            = true
  secret_sync_rotation_interval = "120s"
  database_encryption_key_name  = null

  # n2-standard-8 at a three-node floor is roughly 840/month and the floor is not tunable — the
  # module validates system_node_pool_total_min_nodes >= 3, correctly, because a two-node system
  # pool loses quorum-shaped workloads during a surge upgrade.
  #
  # n2-standard-4 would halve that, and for the ARC CONTROLLER alone it is plainly enough: two
  # replicas at 250m/256Mi each against roughly 2.6 usable vCPU per node once Dataplane V2,
  # managed Prometheus, the Secret Manager CSI driver and the rest of the GKE daemonsets have
  # taken their share. The controller is not what makes the downsize unsafe.
  #
  # WHAT MAKES IT UNSAFE TODAY IS WHAT ELSE LANDS HERE. Every runner scale set in
  # `gitops/arc/values/` declares a nodeSelector and no toleration, so until ../nodepools/runner
  # is applied AND those values gain the matching toleration, runner pods schedule onto this
  # pool. Two things then break on a 4-vCPU node that do not break on an 8-vCPU one:
  #
  #   - Requests. Eleven concurrent runners (build 6 + qualify 4 + canary 1) at 2 vCPU each fit
  #     roughly one to a node here against three on n2-standard-8, so the pool would need ~22
  #     nodes against a ceiling of 9 and jobs would sit Pending with no error that names this.
  #   - Limits. A build runner's memory limit is 16Gi and a presubmit runner's is 24Gi, which is
  #     the whole physical memory of an n2-standard-4. A runner that actually reaches its limit
  #     puts the node under memory pressure and the kubelet starts evicting — including the ARC
  #     controller that is the reason this pool is redundant in the first place.
  #
  # So the change is deferred, not rejected. It becomes a one-line edit once ../nodepools/runner
  # is applied, the gitops runner values tolerate its taint, and a real presubmit load shows no
  # runner pods on this pool. Downsizing before that separation is observed converts a cost
  # saving into a CI outage.
  system_node_pool_machine_type      = "n2-standard-8"
  system_node_pool_total_min_nodes   = 3
  system_node_pool_total_max_nodes   = 9
  system_node_pool_max_pods_per_node = 64
  system_node_pool_boot_disk_size_gb = 100
}
