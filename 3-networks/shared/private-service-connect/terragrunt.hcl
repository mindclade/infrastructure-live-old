# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# PSC endpoints for Google and partner services.
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
  source = "${include.root.locals.module_source_base}//private_service_access?ref=${local.module_version}"
}

locals {
  module_version = "v0.1.0"
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

  # ---------------------------------------------------------------------------------------
  # Consumer endpoints — Google APIs
  # ---------------------------------------------------------------------------------------
  # The global endpoint that backs the DNS forwarding in ../dns-hub. That zone points
  # *.googleapis.com at 199.36.153.8/30; this is what makes an address in that range answer.
  #
  # Both halves are required and neither errors without the other: the zone alone gives
  # NXDOMAIN-free resolution to an address that drops packets, and the endpoint alone is an
  # address nothing resolves to.
  google_api_endpoints = {
    for env in ["development", "staging", "production"] : env => {
      project_id = merge(
        dependency.vpc_development.outputs.host_project_ids,
        dependency.vpc_staging.outputs.host_project_ids,
        dependency.vpc_production.outputs.host_project_ids,
      )[env]
      network = merge(
        dependency.vpc_development.outputs.network_self_link,
        dependency.vpc_staging.outputs.network_self_link,
        dependency.vpc_production.outputs.network_self_link,
      )[env]
      name = "${include.root.locals.prefix}-${env}-googleapis"

      # `all-apis`, not `vpc-sc`. The vpc-sc bundle resolves only the APIs a VPC-SC perimeter
      # protects, which excludes several this estate uses daily; a workload calling one of
      # those gets a connection refused rather than a permission error, which reads like a
      # network fault.
      target = "all-apis"

      # Must sit inside the range ../dns-hub forwards to, or resolution and routing disagree.
      ip_address = "199.36.153.8"
    }
  }

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
  service_attachments = {
    partner-ingress = {
      project_id = dependency.vpc_production.outputs.host_project_ids["production"]
      region     = include.root.locals.region

      description           = "Partner ingress to the production runtime gateway. Manual accept only."
      connection_preference = "ACCEPT_MANUAL"

      # NAT subnet for the attachment. Separate from every workload subnet: traffic arriving
      # here is translated into these addresses, and a firewall rule that wants to say
      # "traffic that came from a partner" has to have an address range to name.
      nat_subnets = ["10.48.241.0/24"]

      # Consumer projects permitted to connect. Empty is correct until a partner is
      # onboarded — an empty allowlist is a closed door, while a missing allowlist under
      # ACCEPT_AUTOMATIC is an open one.
      consumer_accept_lists = {}
    }
  }

  labels = include.root.locals.common_labels
}
