# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Google-personnel access logging.
#
# Access Transparency records when a Google employee accesses customer content — which
# resource, when, and the justification given. It is the only way to answer "has anyone
# outside our organization read this" about data sitting in Google's systems, and the answer
# is otherwise unavailable rather than merely unrecorded.
#
# Two properties worth knowing before reading anything below:
#
#   IT IS NOT RETROACTIVE. Enabling it today says nothing about last month. That is the whole
#   reason this unit exists in 1-org rather than being deferred until a compliance review
#   asks for it.
#
#   ENABLEMENT ITSELF IS NOT TERRAFORM. Access Transparency is switched on per organization
#   through Google support or the console, and requires a support tier that includes it.
#   There is no API and no provider resource. What this unit manages is everything AROUND it:
#   the log routing, the alerting, and the retention that make the records usable.
#
# The enablement step is tracked in docs/runbooks/README.md alongside the other controls
# that have no Terraform surface.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//access_transparency?ref=${local.module_version}"
}

locals {
  module_version = "4d5c0105295bf4a01b770fb75f6a8db5c22c8f79"
}

dependency "kms" {
  config_path = "../kms"

  mock_outputs = {
    crypto_key_ids = {
      logs = "projects/mock/locations/europe-west4/keyRings/mock-global/cryptoKeys/logs"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "common_projects" {
  config_path = "../common-projects"
  mock_outputs = {
    project_ids = {
      logging  = "mc-common-logging"
      security = "mc-common-security"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  org_id     = include.root.locals.org_id
  project_id = dependency.common_projects.outputs.project_ids["security"]

  # ---------------------------------------------------------------------------------------
  # Retention
  # ---------------------------------------------------------------------------------------
  # Seven years, matching the audit archive in bootstrap. Access Transparency entries are
  # low-volume — tens of entries a year on a healthy estate — so the retention costs almost
  # nothing and the alternative is discovering the window was too short during the
  # investigation that needed it.
  sink = {
    name        = "${include.root.locals.prefix}-access-transparency"
    destination = "storage"

    bucket = {
      name           = "${include.root.locals.prefix}-access-transparency"
      location       = include.root.locals.state_location
      encryption_key = dependency.kms.outputs.crypto_key_ids["logs"]
      retention_days = 2555
    }

    filter = <<-EOT
      logName:"logs/cloudaudit.googleapis.com%2Faccess_transparency"
    EOT
  }

  # ---------------------------------------------------------------------------------------
  # Alerting
  # ---------------------------------------------------------------------------------------
  # Every access alerts. Not a threshold, not a daily digest.
  #
  # The volume justifies it — this fires a handful of times a year — and the value of the
  # record is entirely in someone reading it while the support case that prompted it is still
  # open. A weekly summary of Google-personnel access is a document nobody can act on.
  alert = {
    display_name = "Google personnel accessed customer content"
    severity     = "WARNING"

    # No aggregation window: one alert per access, with the justification in the payload.
    filter = <<-EOT
      logName:"logs/cloudaudit.googleapis.com%2Faccess_transparency"
    EOT

    notification_channels = ["security@${include.root.locals.domain}"]

    documentation = <<-EOT
      A Google employee accessed data in this organization. This is usually legitimate — it
      accompanies an open support case, and the justification field says which.

      Check, in order:
        1. Is there an open support case? The `reason` field carries its number.
        2. Does the accessed resource match what the case is about?
        3. Was the access within the window the case was open?

      Any "no" is an incident. The record is in the access-transparency bucket and cannot be
      deleted before its retention expires, so there is no hurry to preserve evidence — but
      there is a reason to ask the question today rather than at the next review.
    EOT
  }

  labels = include.root.locals.common_labels
}
