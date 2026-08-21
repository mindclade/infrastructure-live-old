# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Security Command Center, notification config, and findings export.
#
# SCC's default state is the trap this unit exists to avoid: it is ON, it is generating
# findings, and nothing is reading them. A console tab that nobody opens is not a control —
# it is a record, written after the fact, of what could have been noticed.
#
# So the shape here is: findings go to a Pub/Sub topic, high-severity ones page, everything
# lands in BigQuery next to the audit logs so a query can join them, and muting is declared
# in code with a reason attached rather than clicked away in the UI.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//scc?ref=${local.module_version}"
}

locals {
  module_version = "v0.4.0"
}

dependency "common_projects" {
  config_path = "../common-projects"
  mock_outputs = {
    project_ids = {
      logging  = "mc-common-logging"
      security = "mc-common-security"
    }
    project_numbers = {
      logging  = "000000000001"
      security = "000000000002"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  org_id         = include.root.locals.org_id
  project_id     = dependency.common_projects.outputs.project_ids["security"]
  project_number = dependency.common_projects.outputs.project_numbers["security"]
  location       = include.root.locals.region

  # ---------------------------------------------------------------------------------------
  # Built-in services
  # ---------------------------------------------------------------------------------------
  # Enabled explicitly rather than left at whatever the tier default is, because the default
  # changes with the tier and a silent downgrade is indistinguishable from "no findings".
  services = {
    # Misconfiguration detection. The one that catches a bucket made public by hand.
    security-health-analytics = "ENABLE"

    # Runtime threat detection on GKE nodes: reverse shells, binaries executed from /tmp,
    # crypto-mining. The only source here that sees what a container actually does.
    container-threat-detection = "ENABLE"

    # Anomalous IAM grants, data exfiltration patterns, cryptomining on VMs.
    event-threat-detection = "ENABLE"

    # Reachability-aware CVE analysis. Distinguishes "this image contains a vulnerable
    # library" from "this vulnerable code path is reachable from the internet", which is the
    # difference between a backlog and a page.
    vm-threat-detection = "ENABLE"

    # Web app scanning finds nothing on an estate with no public web surface, and costs per
    # scan. Off, deliberately — turn it on with the first external endpoint.
    web-security-scanner = "DISABLE"
  }

  # ---------------------------------------------------------------------------------------
  # Where findings go
  # ---------------------------------------------------------------------------------------
  notifications = {
    # Everything, to Pub/Sub. This is the machine-readable feed — the export below reads it
    # into BigQuery, and anything else that wants findings subscribes rather than polling.
    all-findings = {
      description = "Every active finding. Consumed by the BigQuery export."
      filter      = "state=\"ACTIVE\""
      pubsub_topic = {
        name = "${include.root.locals.prefix}-scc-findings"
      }
    }

    # High and critical, to the security channel. Deliberately a different destination from
    # the feed above: a stream nobody watches and a page nobody can ignore are different
    # things, and conflating them produces a channel people mute.
    urgent = {
      description = "HIGH and CRITICAL only. Pages the on-call."
      filter      = <<-EOT
        state="ACTIVE"
        AND (severity="HIGH" OR severity="CRITICAL")
        AND NOT mute="MUTED"
      EOT
      pubsub_topic = {
        name = "${include.root.locals.prefix}-scc-urgent"
      }
    }
  }

  # Findings alongside the audit logs in BigQuery. The join that matters: a finding says
  # "this service account has excessive permissions", and the audit dataset says whether it
  # used them.
  bigquery_export = {
    dataset_id = "scc_findings"
    location   = include.root.locals.state_location
    filter     = "state=\"ACTIVE\""
  }

  # ---------------------------------------------------------------------------------------
  # Mutes
  # ---------------------------------------------------------------------------------------
  # Muting in the UI leaves no reason, no owner, and no expiry. Declared here, a mute is a
  # PR that @security reviews — and one that shows up in a diff when it is still present a
  # year later.
  #
  # Every entry states what SCC is reporting and why it is expected. A mute with no reason is
  # a finding somebody found inconvenient.
  mute_configs = {
    break-glass-no-standing-permissions = {
      description = <<-EOT
        SCC flags sa-break-glass as an unused service account. That is its design: it holds
        no standing permissions and is used a handful of times a year. See
        bootstrap/docs/break-glass.md.
      EOT
      filter      = <<-EOT
        category="UNUSED_SERVICE_ACCOUNT"
        AND resource.display_name:"sa-break-glass"
      EOT
    }

    sandbox-external-ip = {
      description = <<-EOT
        The sandbox folder permits external IPs by org-policy exception — see
        1-org/org-policies. SCC reports each one as a public-IP finding.
      EOT
      filter      = <<-EOT
        category="PUBLIC_IP_ADDRESS"
        AND resource.folders.resource_folder_display_name="Sandbox"
      EOT
    }
  }

  labels = include.root.locals.common_labels
}
