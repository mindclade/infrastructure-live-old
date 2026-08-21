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

locals {
  # Immutable source-qualified ARC module commit. Promote to a release tag only by reviewed
  # ref-only change after the module release pipeline publishes the same tree.
  module_version = "v0.4.0"
}

terraform {
  source = "${include.root.locals.module_source_base}//network?ref=${local.module_version}"
}

inputs = {
  networks = {
    arc = {
      project_id                    = dependency.common_projects.outputs.project_ids["ci"]
      network_name                  = "${include.root.locals.prefix}-ci-arc-vpc"
      description                   = "Dedicated private VPC for ARC artifact-authority runners."
      primary_subnet_key            = "arc-nodes"
      create_default_internet_route = true
      subnets = {
        arc-nodes = {
          region        = include.root.locals.region
          ip_cidr_range = "10.240.0.0/20"
          description   = "Private ARC GKE nodes; no public VM addresses."
          secondary_ip_ranges = {
            arc-pods     = "10.241.0.0/16"
            arc-services = "10.242.0.0/20"
          }
          flow_logs = {
            enabled              = true
            aggregation_interval = "INTERVAL_5_SEC"
            sampling             = 1.0
            filter               = "true"
          }
        }
      }
      nat_gateways = {
        arc = {
          region                 = include.root.locals.region
          router_name            = "${include.root.locals.prefix}-ci-arc-router"
          nat_name               = "${include.root.locals.prefix}-ci-arc-nat"
          subnet_keys            = ["arc-nodes"]
          nat_ip_allocate_option = "AUTO_ONLY"
          min_ports_per_vm       = 256
          log_filter             = "ALL"
        }
      }
    }
  }
}
