# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Shared VPC defaults.
#
# Unlike the other files in _envcommon, this one is NOT included from a per-environment
# directory. `3-networks/` sits above the environment level — root.hcl gives its units the
# environment "global" — because a unit per environment would mean three copies of the same
# peering, DNS, and firewall logic kept in step by hand.
#
# So this file does not read env.hcl. It exposes `locals.environments`, and each consuming
# unit fans out over it. That is why every 3-networks unit's outputs are MAPS KEYED BY
# ENVIRONMENT rather than scalars, and why a consumer in 5-workloads indexes them:
#
#   dependency.vpc.outputs.network_self_link[include.envcommon.locals.environment]
#
# A scalar here would mean one VPC shared by development and production, which is precisely
# the boundary the rest of this estate is built to hold.

locals {
  root         = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  prefix         = local.account_vars.locals.prefix
  region         = local.account_vars.locals.region
  module_version = "v0.1.1"

  # ---------------------------------------------------------------------------------------
  # Per-environment settings
  # ---------------------------------------------------------------------------------------
  # Address space is allocated by environment with no overlap, so that a peering or an
  # interconnect added later does not force a renumbering. Renumbering a live VPC means
  # recreating every subnet, which means recreating every cluster in it.
  #
  # /16 per environment, split into a /20 for nodes and two secondary ranges for GKE. The
  # pod range is the one that runs out first: GKE allocates a /24 per node by default, so a
  # /14 is 1024 nodes and a /16 would cap the environment at 256.
  environments = {
    development = {
      cidr           = "10.16.0.0/16"
      pods_cidr      = "10.100.0.0/14"
      services_cidr  = "10.112.0.0/20"
      flow_sampling  = 0.1
      nat_min_ports  = 64
      enable_peering = false
    }
    staging = {
      cidr           = "10.32.0.0/16"
      pods_cidr      = "10.116.0.0/14"
      services_cidr  = "10.120.0.0/20"
      flow_sampling  = 0.1
      nat_min_ports  = 64
      enable_peering = false
    }
    production = {
      cidr          = "10.48.0.0/16"
      pods_cidr     = "10.128.0.0/14"
      services_cidr = "10.144.0.0/20"
      # Half of production's flows, against a tenth elsewhere. Flow logs are expensive at
      # full sampling and are the only way to answer "what talked to what" after an incident;
      # 0.5 is the usual compromise, and the environment where that question gets asked is
      # the one that pays for it.
      flow_sampling = 0.5
      # More ports per VM: a production node fans out to more distinct destinations, and NAT
      # port exhaustion presents as intermittent connection timeouts rather than as an error
      # that names NAT.
      nat_min_ports  = 256
      enable_peering = false
    }
  }
}

terraform {
  source = "${local.root.locals.module_source_base}//network?ref=${local.module_version}"
}

inputs = {
  # Custom subnets only. Auto-mode creates a subnet in every region with predictable ranges,
  # which both wastes address space and quietly places resources outside the residency
  # allowlist in gcp.resourceLocations.
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  region = local.region

  enable_flow_logs  = true
  flow_log_interval = "INTERVAL_10_MIN"
  flow_log_metadata = "INCLUDE_ALL_METADATA"

  # Private Google Access: reach Google APIs without an external IP, which is mandatory given
  # the org-wide external-IP denial in bootstrap.
  private_ip_google_access = true

  # Keep the local 0.0.0.0/0 route whose next hop is the default internet gateway. Public
  # Cloud NAT requires that route even for nodes without external addresses, and the
  # private/restricted Google API VIPs use it as their next hop as well. The route is not an
  # egress allow: firewall-baseline denies 0.0.0.0/0 after its explicit destination allows.
  delete_default_routes_on_create = false

  labels = local.root.locals.common_labels
}
