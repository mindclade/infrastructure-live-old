# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# The reserved internal address every application hostname resolves to.
#
# One per environment, and the single VIP behind `mindclade.studio`, `*.mindclade.ai`, and
# `*.mindclade.dev` in that environment. The GKE Gateway binds to it by NAME; the private DNS
# zones in ../dns-hub point their A records at its VALUE. Both of those are read from this
# unit's outputs rather than restated, because a VIP that moves and a DNS record that does not
# is an outage with no error anywhere.
#
# ---------------------------------------------------------------------------------------
# Why this is not allocated from the `internal-lb` subnet
# ---------------------------------------------------------------------------------------
# `internal-lb` is a REGIONAL_MANAGED_PROXY subnet. That is where the regional internal
# Application Load Balancer materialises its Envoy proxies — it holds PROXIES, not addresses,
# and nothing can be allocated from it. Both belong to the same load balancer, which is
# exactly what makes the mistake natural: the obvious reading of "the subnet the internal ALB
# uses" is wrong here, and the API's rejection names the purpose without explaining it.
#
# The address therefore comes from `gateway-vip`, an ordinary PRIVATE subnet that exists for
# this and for the internal load balancers that follow.
#
# Split out of a single spanning unit that covered all three environments in ONE state file.
# The shared configuration still comes from `_envcommon/vpc.hcl`, so the drift that design
# prevented still cannot happen; what changed is that development and production are no longer
# the same plan, the same lock, and the same blast radius. See docs/module-interface-contract.md.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//internal_address?ref=${local.module_version}"
}

locals {
  environment = include.root.locals.environment

  module_version = "v0.1.0"
}

dependency "vpc" {
  config_path = "../shared-vpc-host"

  # EVERY OUTPUT HERE IS KEYED BY ENVIRONMENT — 3-networks is one unit covering all three.
  # `subnet_self_links` is additionally nested by subnet key, so it is indexed twice.
  mock_outputs = {
    host_project_ids = {
      development = "mc-development-net"
      staging     = "mc-staging-net"
      production  = "mc-production-net"
    }
    subnet_self_links = {
      development = { gateway-vip = "projects/mock/regions/europe-west4/subnetworks/gateway-vip" }
      staging     = { gateway-vip = "projects/mock/regions/europe-west4/subnetworks/gateway-vip" }
      production  = { gateway-vip = "projects/mock/regions/europe-west4/subnetworks/gateway-vip" }
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  addresses = {
    (local.environment) = {
      project_id = dependency.vpc.outputs.host_project_ids[local.environment]
      region     = include.root.locals.region

      # THE NAME IS AN INTERFACE, not a label. The Gateway in the monorepo's
      # infra/kubernetes/platform/gateway names this exact string:
      #
      #   spec:
      #     addresses:
      #       - type: NamedAddress
      #         value: mc-<env>-mindclade-internal-vip
      #
      # Nothing on the Argo side generates it. Renaming it here alone leaves a Gateway that
      # never receives an address, and the only symptom is a status that never becomes
      # programmed — no event, no error, nothing in any workload's logs.
      name = "${include.root.locals.prefix}-${local.environment}-mindclade-internal-vip"

      # The PRIVATE subnet, not the proxy-only one. See the note at the top of this file.
      subnetwork = dependency.vpc.outputs.subnet_self_links[local.environment]["gateway-vip"]

      description = "Internal VIP for mindclade.studio, *.mindclade.ai, and *.mindclade.dev in ${local.environment}."
    }
  }
}
