# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Private Service Access ranges, with PSC activation gates for future partner services.
#
# Two distinct things share the name "Private Service Connect", and conflating them is the
# usual source of confusion here:
#
#   CONSUMER endpoints — an address inside our VPC that forwards to a service somewhere else.
#     This is how a managed service (Cloud SQL, a partner's API) is reached without either
#     side having a route to the other's network.
#
#   PRODUCER attachments — an address someone else creates in THEIR VPC that forwards into
#     ours. This is how a partner reaches a service we run, without us peering to them.
#
# Both are below. Peering is deliberately absent from this estate: a peering makes two
# networks mutually routable and cannot be scoped to one service, so a partner peering would
# put their network one firewall rule away from every workload we run.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//private_connectivity?ref=${local.module_version}"
}

locals {
  module_version = "v0.4.0"
}

# One dependency per environment. This unit genuinely spans all three — a peering range is
# reserved per environment out of one address plan — so unlike cloud-nat or firewall-baseline
# it is not split. What changed is that each environment's VPC is now a separate state, so
# these are three named dependencies rather than one map-valued output.
dependency "vpc_development" {
  config_path = "../../development/shared-vpc-host"

  mock_outputs = {
    host_project_ids = {
      development = "mc-development-net"
    }
    network_self_link = {
      development = "projects/mock/global/networks/mock-development-vpc"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "vpc_staging" {
  config_path = "../../staging/shared-vpc-host"

  mock_outputs = {
    host_project_ids = {
      staging = "mc-staging-net"
    }
    network_self_link = {
      staging = "projects/mock/global/networks/mock-staging-vpc"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "vpc_production" {
  config_path = "../../production/shared-vpc-host"

  mock_outputs = {
    host_project_ids = {
      production = "mc-production-net"
    }
    network_self_link = {
      production = "projects/mock/global/networks/mock-production-vpc"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  # ---------------------------------------------------------------------------------------
  # Service networking ranges
  # ---------------------------------------------------------------------------------------
  # The /24 each managed service allocates from. Reserved per environment out of the same
  # /16 the subnets come from, so the address plan stays in one place — see
  # _envcommon/vpc.hcl.
  #
  # A /24 rather than the /16 Google's documentation suggests: the larger range is sized for
  # an estate with dozens of managed-service instances, and reserving it costs the address
  # space that would otherwise carry a second GKE cluster.
  service_networking = {
    development = {
      project_id      = dependency.vpc_development.outputs.host_project_ids["development"]
      network         = dependency.vpc_development.outputs.network_self_link["development"]
      allocated_range = "10.16.240.0/24"
    }
    staging = {
      project_id      = dependency.vpc_staging.outputs.host_project_ids["staging"]
      network         = dependency.vpc_staging.outputs.network_self_link["staging"]
      allocated_range = "10.32.240.0/24"
    }
    production = {
      project_id      = dependency.vpc_production.outputs.host_project_ids["production"]
      network         = dependency.vpc_production.outputs.network_self_link["production"]
      allocated_range = "10.48.240.0/24"
    }
  }

  # Google API private/restricted VIPs are routed service addresses, not consumer PSC
  # forwarding rules. dns-hub owns the private DNS mapping to restricted.googleapis.com.
  google_api_endpoints = {}

  # ---------------------------------------------------------------------------------------
  # Producer attachments — partner ingress
  # ---------------------------------------------------------------------------------------
  # How a partner reaches a service we run. Production only: there is no reason for a partner
  # to have a path into development, and creating one "for testing" is how it becomes
  # permanent.
  #
  # ACCEPT_MANUAL, not ACCEPT_AUTOMATIC. Automatic accepts a connection from any project that
  # knows the attachment name, which is not a secret — it appears in the partner's own
  # Terraform. Manual means each consumer project is named here, and onboarding a partner is
  # a reviewed change rather than a URL they were given.
  # A producer attachment is not valid without a real forwarding-rule target, a separately
  # created PSC NAT subnet, and an approved consumer project. Partner onboarding adds all
  # three in one reviewed change; the foundation does not create a half-configured service.
  service_attachments = {}

  labels = include.root.locals.common_labels
}
