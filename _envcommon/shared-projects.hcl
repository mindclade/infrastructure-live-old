# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Shared defaults for a 2-environments/<env>/shared-projects unit.
#
# Two projects per environment, created identically in all three so that staging is a
# rehearsal for production rather than an approximation of it. What differs per environment
# is the budget and, in development, a couple of preview APIs — everything else is here.

locals {
  root         = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  environment    = local.env_vars.locals.environment
  prefix         = local.account_vars.locals.prefix
  module_version = "v0.4.0"
}

terraform {
  source = "${local.root.locals.module_source_base}//project_factory?ref=${local.module_version}"
}

inputs = {
  billing_account = local.account_vars.locals.billing_account

  projects = {
    # ------------------------------------------------------------------------------------
    # Shared VPC host
    # ------------------------------------------------------------------------------------
    # No workloads, ever. A workload here holds ambient network admin over every service
    # project attached to the host, and that grant is invisible when reading the service
    # project's own IAM policy.
    net = {
      project_id = "${local.prefix}-${local.environment}-net"
      name       = "${local.environment} shared VPC host"

      services = [
        "compute.googleapis.com",
        "dns.googleapis.com",
        "servicenetworking.googleapis.com",
        "networkmanagement.googleapis.com",
        "networksecurity.googleapis.com",
      ]

      # Marks it as a Shared VPC host. 3-networks builds the network inside it and
      # 4-projects attaches service projects to it.
      shared_vpc_host = true

      # A lien, so the project cannot be deleted while service projects are attached. The
      # failure it prevents is a whole environment losing its network in one API call.
      lien = true
    }

    # ------------------------------------------------------------------------------------
    # Shared operations
    # ------------------------------------------------------------------------------------
    ops = {
      project_id = "${local.prefix}-${local.environment}-ops"
      name       = "${local.environment} shared operations"

      services = [
        "monitoring.googleapis.com",
        "logging.googleapis.com",
        "cloudtrace.googleapis.com",
        "cloudprofiler.googleapis.com",
        "artifactregistry.googleapis.com",
        "dns.googleapis.com",
      ]

      # The metrics scope for the environment. Every workload project in this environment
      # writes here, so one dashboard covers the environment instead of one per project.
      monitoring_scope_host = true
    }

    # ------------------------------------------------------------------------------------
    # Platform
    # ------------------------------------------------------------------------------------
    # Holds the environment's GKE cluster and everything scheduled on it.
    #
    # One cluster per environment, not one per workload domain. Domain isolation happens at
    # the namespace and AppProject level — see gitops/projects/ — because five clusters per
    # environment means five control planes to upgrade, five sets of node pools sitting idle,
    # and a GPU pool that cannot be shared between research and serving even when one is
    # empty and the other is queued.
    #
    # The domain projects in 4-projects hold each domain's DATA. The cluster that reads it
    # lives here, and reaches it as a Workload Identity principal rather than by being in the
    # same project.
    platform = {
      project_id = "${local.prefix}-${local.environment}-platform"
      name       = "${local.environment} platform"

      services = [
        "container.googleapis.com",
        "containersecurity.googleapis.com",
        "binaryauthorization.googleapis.com",
        "containeranalysis.googleapis.com",
        "artifactregistry.googleapis.com",
        "certificatemanager.googleapis.com",
        "secretmanager.googleapis.com",
        "cloudkms.googleapis.com",
        "monitoring.googleapis.com",
        "logging.googleapis.com",
        "gkebackup.googleapis.com",
      ]

      # Attached to the environment's Shared VPC as a service project. The cluster's nodes
      # take addresses from the host project's subnets, so the network is governed in
      # 3-networks and consumed here.
      shared_vpc_service_project = true
    }
  }

  # Deleting an environment's shared projects is not something that should be possible as a
  # side effect of a refactor. Production additionally inherits stricter organization policy from its
  # infrastructure-live-owned folder.
  deletion_policy = "PREVENT"

  labels = merge(local.root.locals.common_labels, {
    environment = local.environment
    shared      = "true"
  })
}
