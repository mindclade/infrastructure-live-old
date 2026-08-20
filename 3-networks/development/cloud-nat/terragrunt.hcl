# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Egress NAT. Required because external IPs are denied org-wide.
#
# `compute.vmExternalIpAccess` is deny-all in `1-org/org-policies`, so no node, pod, or VM has a
# route off the network without this. That makes NAT load-bearing rather than convenient: an
# outage here is every image pull, every package install, and every outbound API call failing
# at once, with an error that says "connection timed out" and names nothing.
#
# One NAT per environment, in the environment's own host project. Sharing one across
# environments would put development's traffic behind production's source addresses, which
# breaks every allowlist a partner maintains on the far side.
#
# Split out of a single spanning unit that covered all three environments in ONE state file.
# The shared configuration still comes from `_envcommon/vpc.hcl`, so the drift that design
# prevented still cannot happen; what changed is that development and production are no longer
# the same plan, the same lock, and the same blast radius. See docs/module-interface-contract.md.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/vpc.hcl"
  expose         = true
  merge_strategy = "deep"
}

dependency "vpc" {
  config_path = "../shared-vpc-host"

  mock_outputs = {
    host_project_ids = {
      development = "mc-development-net"
      staging     = "mc-staging-net"
      production  = "mc-production-net"
    }
    network_self_link = {
      development = "projects/mock/global/networks/mock-development-vpc"
      staging     = "projects/mock/global/networks/mock-staging-vpc"
      production  = "projects/mock/global/networks/mock-production-vpc"
    }
    subnetwork_names = {
      development = "mc-development-nodes"
      staging     = "mc-staging-nodes"
      production  = "mc-production-nodes"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  environment = include.root.locals.environment
  cfg         = include.envcommon.locals.environments[local.environment]
  module_version = "v0.2.0"
}

terraform {
  source = "${include.root.locals.module_source_base}//cloud_nat?ref=${local.module_version}"
}

inputs = {
  nats = {
    (local.environment) = {
      project_id = dependency.vpc.outputs.host_project_ids[local.environment]
      network    = dependency.vpc.outputs.network_self_link[local.environment]
      region     = include.root.locals.region

      router_name = "${include.root.locals.prefix}-${local.environment}-router"
      nat_name    = "${include.root.locals.prefix}-${local.environment}-nat"

      # STATIC addresses, not auto-allocated.
      #
      # Auto-allocation gives NAT an address from a Google pool that changes whenever the NAT
      # scales, which means our egress IP is not something a partner can allowlist. Reserving
      # them makes the egress surface a fixed, documentable set — and makes "which of our
      # environments called you" answerable from the other side.
      nat_ip_allocate_option = "MANUAL_ONLY"
      static_ip_count        = local.environment == "production" ? 4 : 2

      # Every subnet's primary range AND its secondary ranges. Omitting the secondaries is
      # the classic mistake here: nodes reach the internet, pods do not, and the symptom is
      # that image pulls work while application egress hangs.
      source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

      # Port allocation. The default 64 ports per VM is exhausted by a node opening
      # connections to many distinct destinations — which is exactly what a training job
      # streaming from object storage does. Exhaustion presents as intermittent timeouts,
      # never as an error naming NAT, so it is worth over-provisioning.
      min_ports_per_vm               = local.cfg.nat_min_ports
      enable_dynamic_port_allocation = true
      max_ports_per_vm               = local.cfg.nat_min_ports * 8

      # Timeouts below the defaults. A NAT mapping held for the default 30 minutes after a
      # TCP connection closes is a port that cannot be reused, which brings exhaustion
      # forward for no benefit.
      tcp_established_idle_timeout_sec = 1200
      tcp_transitory_idle_timeout_sec  = 30
      udp_idle_timeout_sec             = 30
      icmp_idle_timeout_sec            = 30

      # ERRORS_ONLY, not ALL. Logging every translated connection on a GPU fleet produces
      # more log volume than the application logs and answers no question — the entries that
      # matter are the drops, which are what "we ran out of ports" looks like in a log.
      log_config = {
        enable = true
        filter = "ERRORS_ONLY"
      }
    }
  }
}
