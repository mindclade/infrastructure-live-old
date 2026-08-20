# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Dedicated or Partner Interconnect, if and when on-prem or colo GPU exists.
#
# DELIBERATELY EXCLUDED, and this is the one unit in the repository where that is a permanent
# state rather than scaffolding. Everything else that carried an `exclude` block did so
# because its inputs were unwritten; this one is written and excluded because applying it
# provisions billed circuits.
#
# A Dedicated Interconnect is a physical cross-connect in a colocation facility. Terraform
# can create the GCP half, but the LOA-CFA has to be handed to the facility and the fibre has
# to be patched by a human before anything carries a packet — and Google bills for the
# reserved capacity from the moment the attachment exists, whether or not the circuit is up.
#
# Remove the exclude block when ALL of these are true:
#   1. A colocation facility is contracted and the cross-connect is ordered.
#   2. `interconnect_locations` below names the real facilities, from:
#        gcloud compute interconnects locations list
#   3. The peer ASN is agreed with whoever runs the far side.
#   4. Somebody has read the redundancy note below and accepted the single-circuit risk, or
#      provisioned the second circuit.
#
# Until then it plans clean and applies nothing, which is what keeps `run --all` honest.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//network?ref=${local.module_version}"
}

locals {
  module_version = "v0.1.0"
}

exclude {
  if      = true
  actions = ["all"]

  # false, unlike the scaffolding units this replaced: ../shared-vpc-host is a real unit that
  # other things depend on, and excluding it along with this one would take the whole network
  # stage out of `run --all`.
  exclude_dependencies = false
}

dependency "vpc" {
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
  project_id = dependency.vpc.outputs.host_project_ids["production"]
  network    = dependency.vpc.outputs.network_self_link["production"]
  region     = include.root.locals.region

  # ---------------------------------------------------------------------------------------
  # Redundancy
  # ---------------------------------------------------------------------------------------
  # TWO circuits, in two different facilities, on two different Cloud Router interfaces.
  #
  # This is not belt-and-braces. Google's Interconnect SLA does not apply to a single
  # circuit at all — a one-circuit deployment has no SLA, and its documented availability is
  # "maintenance will take it down". Anyone reading this because the second circuit looks
  # like an easy saving should know that removing it does not degrade the SLA, it removes it.
  interconnects = {
    primary = {
      name        = "${include.root.locals.prefix}-ic-primary"
      location    = "PLACEHOLDER-ams-zone1-1"
      description = "Primary circuit. Replace location before removing the exclude block."

      # 10G. The number that matters for a GPU estate is not throughput but whether the
      # circuit carries training data at all — if it does, size it from the dataset and the
      # epoch time, not from a default.
      link_type            = "LINK_TYPE_ETHERNET_10G_LR"
      requested_link_count = 1
    }

    secondary = {
      name        = "${include.root.locals.prefix}-ic-secondary"
      location    = "PLACEHOLDER-ams-zone2-1"
      description = "Secondary circuit. A DIFFERENT availability zone — see the note above."

      link_type            = "LINK_TYPE_ETHERNET_10G_LR"
      requested_link_count = 1
    }
  }

  # ---------------------------------------------------------------------------------------
  # BGP
  # ---------------------------------------------------------------------------------------
  cloud_router = {
    name = "${include.root.locals.prefix}-ic-router"

    # A private ASN from the documented range. Must not collide with the peer's.
    asn = 64512

    # Advertise the production ranges only, and name them explicitly.
    #
    # DEFAULT advertisement mode would announce every subnet in the VPC, including any added
    # later — so a subnet created for an unrelated purpose would become reachable from the
    # colo with no change here and nothing in a diff.
    advertise_mode = "CUSTOM"
    advertised_ip_ranges = [
      { range = "10.48.0.0/16", description = "production nodes and services" },
    ]
  }

  # MD5 authentication on the BGP session. Optional in the sense that the session comes up
  # without it, which is exactly why it gets skipped — an unauthenticated session accepts
  # routes from anything that reaches the interface.
  bgp_md5_authentication = true

  # MACsec on the physical link. Only available on Dedicated Interconnect, and the reason to
  # prefer Dedicated over Partner when the traffic is training data: without it, the bytes on
  # the cross-connect are in the clear inside the facility.
  macsec_enabled = true

  labels = include.root.locals.common_labels
}
