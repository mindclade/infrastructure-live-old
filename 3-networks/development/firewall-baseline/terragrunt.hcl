# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Default-deny egress with an explicit allow list.
#
# Default-deny INGRESS is what GCP already does, and it is the easy half. This unit is about
# EGRESS, which GCP leaves wide open by default — every VM can reach every address on the
# internet, and nothing about the network says so.
#
# Egress control is the difference between "an attacker got code execution on a node" and
# "an attacker got code execution on a node and exfiltrated the checkpoint bucket". It is
# also the control most likely to break something at 3am, so the ordering below matters:
# the deny rule is at the LOWEST priority and every allow sits above it, which means adding
# a legitimate destination is one rule and never a change to the deny.
#
# Rules are declared here rather than per-environment because a firewall difference between
# staging and production makes staging stop being a rehearsal. What differs is which
# environments a rule applies to, stated per rule.
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
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  environment    = include.root.locals.environment
  module_version = "v0.4.0"

  # Priorities. Spaced so a rule can be inserted between two without renumbering — GCP
  # evaluates lowest first, and renumbering a live firewall is a window during which the
  # order is whatever the apply happened to reach.
  #
  #   1000  health checks and Google infrastructure
  #   1100  intra-VPC
  #   1200  Google APIs via Private Google Access
  #   1300  named external destinations
  #   65000 deny everything else
  rules = {
    # ------------------------------------------------------------------------------------
    # Ingress
    # ------------------------------------------------------------------------------------
    # Google's health-check and load-balancer ranges. Without these a backend is marked
    # unhealthy and removed, which presents as a service that is up and receiving no traffic.
    allow-health-checks = {
      direction     = "INGRESS"
      priority      = 1000
      action        = "allow"
      source_ranges = ["35.191.0.0/16", "130.211.0.0/22"]
      target_tags   = ["gke-node"]
      allow         = [{ protocol = "tcp" }]
      description   = "GCLB and health-check probers. Removing this silently drains every backend."
    }

    # The GKE control plane reaching webhooks on nodes. Admission webhooks — including Policy
    # Controller's — are called by the API server, and a blocked call fails the admission
    # request rather than being skipped.
    allow-control-plane-webhooks = {
      direction     = "INGRESS"
      priority      = 1000
      action        = "allow"
      source_ranges = ["172.16.0.0/28"]
      target_tags   = ["gke-node"]
      allow         = [{ protocol = "tcp", ports = ["443", "8443", "9443", "15017"] }]
      description   = "GKE control plane to admission and conversion webhooks."
    }

    # IAP TCP forwarding to the developer workstation, and only to it.
    #
    # This implements the `required_firewall_rule` contract published by
    # 5-workloads/development/workstation, which sets `create_iap_ssh_firewall_rule = false`.
    # The module creates its firewall rule in the project that owns the INSTANCE, and the
    # workstation lives in the `platform` service project while this network lives in the host
    # project — so the rule has to be owned here. The tag is the join between the two files and
    # renaming it in one place produces an instance that passes every IAM check and then times
    # out at connect.
    #
    # 35.235.240.0/20 is Google's single published range for IAP TCP forwarding. It is written
    # literally rather than taken from a variable: a configurable source range is how a rule that
    # exists to admit only IAP eventually admits 0.0.0.0/0.
    #
    # Development-only, because the workstation is development-only. This is the one place a
    # per-environment firewall difference is not a rehearsal gap — production growing this rule
    # without a production workstation would be an open SSH path to nothing.
    allow-iap-ssh-workstation = {
      direction     = "INGRESS"
      priority      = 1000
      action        = "allow"
      source_ranges = ["35.235.240.0/20"]
      target_tags   = ["development-workstation-iap-ssh"]
      allow         = [{ protocol = "tcp", ports = ["22"] }]
      log_config    = { metadata = "INCLUDE_ALL_METADATA" }
      description   = "IAP TCP forwarding to the developer workstation. Human SSH is the only path in."
    }

    # ------------------------------------------------------------------------------------
    # Egress — allowed, in priority order
    # ------------------------------------------------------------------------------------
    # Inside the VPC. Pod-to-pod and pod-to-service traffic never leaves, and network policy
    # inside the cluster is where east-west restriction belongs — a firewall rule cannot see
    # pod identity.
    allow-egress-intra-vpc = {
      direction          = "EGRESS"
      priority           = 1100
      action             = "allow"
      destination_ranges = ["10.0.0.0/8"]
      allow              = [{ protocol = "all" }]
      description        = "Intra-VPC. East-west restriction is NetworkPolicy's job, not this one."
    }

    # Google APIs through Private Google Access. This one range covers Cloud Storage,
    # Artifact Registry, Secret Manager, Logging, and the rest — the whole reason nodes need
    # no external address at all.
    allow-egress-google-apis = {
      direction          = "EGRESS"
      priority           = 1200
      action             = "allow"
      destination_ranges = ["199.36.153.4/30", "34.126.0.0/18"] # restricted.googleapis.com + direct connectivity
      allow              = [{ protocol = "tcp", ports = ["443"] }]
      description        = "restricted.googleapis.com and supported direct-connect API endpoints."
    }

    # DNS to the metadata server. Blocking it breaks name resolution before anything else
    # has a chance to fail, and the symptom is every outbound call timing out.
    allow-egress-metadata = {
      direction          = "EGRESS"
      priority           = 1200
      action             = "allow"
      destination_ranges = ["169.254.169.254/32"]
      allow              = [{ protocol = "tcp", ports = ["80", "988"] }, { protocol = "udp", ports = ["53"] }]
      description        = "Metadata server: DNS, Workload Identity token exchange."
    }

    # ------------------------------------------------------------------------------------
    # Egress — the deny
    # ------------------------------------------------------------------------------------
    # Lowest priority, so every rule above wins. This is the rule the unit exists for.
    #
    # Logged, and that is not optional: a denied egress is indistinguishable from a hung
    # connection from inside the pod, and without the log the first hour of the incident is
    # spent proving the firewall is involved at all.
    #
    # THIS RULE IS UNDER STANDING PRESSURE. `5-workloads/development/workstation` cannot finish
    # provisioning because its startup script fetches Debian packages and the Nix installer from
    # the open internet, and the obvious way to make that boot is a rule above this one that
    # admits a CDN range — or this one turned into an allow. Both are refused;
    # `contracts/workstation-egress.json` records why, and
    # `scripts/validate_workstation_egress.py` fails any egress allow in this tree that names a
    # destination the contract has not reviewed. The reviewed answer adds no destination: it
    # serves those packages from inside the perimeter over the restricted VIP already allowed at
    # priority 1200.
    deny-egress-default = {
      direction          = "EGRESS"
      priority           = 65000
      action             = "deny"
      destination_ranges = ["0.0.0.0/0"]
      deny               = [{ protocol = "all" }]
      log_config         = { metadata = "INCLUDE_ALL_METADATA" }
      description        = "Default deny. Everything reachable is named in a rule above this one."
    }
  }
}

terraform {
  source = "${include.root.locals.module_source_base}//firewall?ref=${local.module_version}"
}

inputs = {
  firewalls = {
    (local.environment) = {
      project_id = dependency.vpc.outputs.host_project_ids[local.environment]
      network    = dependency.vpc.outputs.network_self_link[local.environment]

      rules = local.rules

      # Firewall Rules Logging on the deny rule only. Logging every allow on a GPU fleet
      # produces volume without signal — see the exclusions in 1-org/log-sinks — while the
      # denies are the entries anyone will ever read.
      enable_logging_on_deny_only = true
    }
  }
}
