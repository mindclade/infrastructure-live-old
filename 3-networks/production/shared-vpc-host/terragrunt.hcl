# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# Shared VPC host network for production.
#
# Split out of the former single `3-networks/shared-vpc-host`, which built all three
# environments' VPCs in ONE state file. The subnet layout is still computed from one table —
# `_envcommon/vpc.hcl`'s `environments` map — so the drift that design was protecting against
# still cannot happen. What changed is that development and production are no longer the same
# plan, the same lock, and the same blast radius. See docs/module-interface-contract.md.
#
# Outputs remain MAPS KEYED BY ENVIRONMENT, with one entry. Consumers already index them by
# their own environment, so nothing downstream changes shape:
#
#   network = dependency.vpc.outputs.network_self_link[include.envcommon.locals.environment]
#
# The host project itself is created in 2-environments/production; this unit builds the network
# inside it and attaches nothing. Service projects attach in 4-projects.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/vpc.hcl"
  expose         = true
  merge_strategy = "deep"
}

# One dependency, not three. Terragrunt builds the apply order from it, so the network cannot
# be created before the project that holds it.
dependency "shared" {
  config_path = "../../../2-environments/production/shared-projects"

  mock_outputs = {
    project_ids = {
      net = "mc-production-net"
      ops = "mc-production-ops"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  environment = include.root.locals.environment
  cfg         = include.envcommon.locals.environments[local.environment]
}

inputs = {
  networks = {
    (local.environment) = {
      project_id   = dependency.shared.outputs.project_ids["net"]
      network_name = "${include.root.locals.prefix}-${local.environment}-vpc"

      # Flow-log sampling is a per-SUBNET setting, not a per-network one, and it differs by
      # purpose: a proxy-only subnet cannot carry flow logs at all. It is therefore applied
      # inside each subnet below rather than once here.

      subnets = {
        # One node subnet per environment. GKE takes its pod and service addresses from the
        # secondary ranges below rather than from this one, so a /20 is generous for nodes
        # even at a few hundred of them.
        nodes = {
          ip_cidr_range = cidrsubnet(local.cfg.cidr, 4, 0)
          region        = include.root.locals.region

          secondary_ip_ranges = {
            # The names here are the contract with 5-workloads/<env>/gke, which passes them
            # as ip_range_pods and ip_range_services. Renaming one produces a cluster
            # creation failure that names the range and not this file.
            "${include.root.locals.prefix}-${local.environment}-pods"     = local.cfg.pods_cidr
            "${include.root.locals.prefix}-${local.environment}-services" = local.cfg.services_cidr
          }

          flow_logs = {
            enabled  = true
            sampling = local.cfg.flow_sampling
            interval = "INTERVAL_10_MIN"
          }
        }

        # The proxy-only subnet. This is where the regional internal Application Load Balancer
        # materialises its Envoy fleet — it holds PROXIES, not addresses, so nothing can be
        # allocated from it. The Gateway's VIP therefore cannot come from here; that is what
        # `gateway-vip` below is for, and conflating the two is the most natural mistake to
        # make when reading `gke-l7-rilb`'s requirements.
        #
        # No flow logs and no secondary ranges: the API rejects both on this purpose, and the
        # module now refuses at plan time rather than letting the apply discover it.
        internal-lb = {
          ip_cidr_range = cidrsubnet(local.cfg.cidr, 8, 32)
          region        = include.root.locals.region
          purpose       = "REGIONAL_MANAGED_PROXY"
          role          = "ACTIVE"

          flow_logs = { enabled = false }
        }

        # The Gateway VIP is reserved out of this one, by ../gateway-vip. Kept apart from
        # `nodes` so that a firewall rule scoped to "where services are exposed" does not also
        # cover every node, and apart from `internal-lb` because that subnet cannot hold an
        # address at all.
        #
        # A /24 for what is currently one address, because a subnet cannot be resized without
        # recreating it and the next internal load balancer should not need a new one.
        gateway-vip = {
          ip_cidr_range = cidrsubnet(local.cfg.cidr, 8, 33)
          region        = include.root.locals.region

          flow_logs = {
            enabled  = true
            sampling = local.cfg.flow_sampling
            interval = "INTERVAL_10_MIN"
          }
        }
      }
    }
  }
}
