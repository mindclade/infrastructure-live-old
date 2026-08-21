# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Org-wide sinks beyond the audit export: application logs, 400d hot / 7y cold.
#
# The organization layer exports AUDIT logs centrally — who did what — to BigQuery and GCS. This unit
# covers everything else: application logs, GKE container output, VPC flow logs, and the
# Policy Controller denials that say why a pod never started.
#
# The two-tier split is a cost decision, and the numbers are not arbitrary. Application log
# volume at GPU-training scale is dominated by a handful of chatty sources; keeping 400 days
# of everything in a log bucket costs multiples of keeping 30 days hot and the rest in
# Coldline GCS, and nobody has ever queried a 200-day-old debug line interactively.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//log_sink?ref=${local.module_version}"
}

locals {
  module_version = "v0.4.0"

  # Excluded from every sink below. These are high-volume and answer nothing an incident
  # review asks: the load balancer's own health probes, and the readiness/liveness traffic
  # GKE generates against every pod, every few seconds, forever.
  #
  # Excluding at the SINK rather than at the source is deliberate — the entries still exist
  # in the project's _Default bucket for 30 days if someone genuinely needs them.
  noise_exclusions = [
    {
      name        = "health-checks"
      description = "GCLB and kubelet probe traffic. Volume without signal."
      filter      = <<-EOT
        resource.type="http_load_balancer"
        AND httpRequest.userAgent=~"GoogleHC|kube-probe"
      EOT
    },
    {
      name        = "gke-system-chatter"
      description = "Leader-election and informer resync from kube-system."
      filter      = <<-EOT
        resource.type="k8s_container"
        AND resource.labels.namespace_name="kube-system"
        AND severity < WARNING
      EOT
    },
  ]
}

# CMEK for the archive bucket, from the `global` keyring.
dependency "kms" {
  config_path = "../kms"

  mock_outputs = {
    crypto_key_ids = {
      logs = "projects/mock/locations/us-central1/keyRings/mock-global/cryptoKeys/logs"
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
  parent           = "organizations/${include.root.locals.org_id}"
  project_id       = dependency.common_projects.outputs.project_ids["logging"]
  include_children = true

  sinks = {
    # ------------------------------------------------------------------------------------
    # Hot: 30 days, queryable, in a log bucket
    # ------------------------------------------------------------------------------------
    application-hot = {
      description = "Application and platform logs. The tier anyone actually queries."
      destination = "logging"

      # Log Analytics turns the bucket into something SQL can reach, which is the difference
      # between "grep the console" and "join this against the audit dataset".
      enable_analytics = true
      retention_days   = 30

      filter = <<-EOT
        (resource.type="k8s_container" OR resource.type="k8s_pod" OR resource.type="gke_cluster")
        AND NOT logName:"logs/cloudaudit.googleapis.com"
      EOT

      exclusions = local.noise_exclusions
    }

    # Policy Controller denials. Their own sink, with no exclusions and a longer window,
    # because "why did this pod never start" is asked days later and the answer is one line
    # that the noise filters above would otherwise be free to drop.
    admission-denials = {
      description      = "Gatekeeper and Binary Authorization denials. Small, high value."
      destination      = "logging"
      enable_analytics = true
      retention_days   = 400

      filter = <<-EOT
        protoPayload.serviceName="binaryauthorization.googleapis.com"
        OR (resource.type="k8s_cluster" AND protoPayload.response.reason="Forbidden"
            AND protoPayload.response.message:"denied by")
      EOT
    }

    # ------------------------------------------------------------------------------------
    # Cold: seven years, in GCS
    # ------------------------------------------------------------------------------------
    application-archive = {
      description = "Everything the hot tier holds, kept for seven years in Coldline."
      destination = "storage"

      bucket = {
        name           = "${include.root.locals.prefix}-app-logs-archive"
        location       = include.root.locals.state_location
        encryption_key = dependency.kms.outputs.crypto_key_ids["logs"]

        # Storage class transitions rather than a single class: a log read in week one is
        # read at Standard prices, and one read in year six is read at all.
        lifecycle_rules = [
          { age = 30, action = "SetStorageClass", storage_class = "NEARLINE" },
          { age = 90, action = "SetStorageClass", storage_class = "COLDLINE" },
          { age = 365, action = "SetStorageClass", storage_class = "ARCHIVE" },
        ]

        retention_days = 2555 # seven years
      }

      filter = <<-EOT
        (resource.type="k8s_container" OR resource.type="k8s_pod" OR resource.type="gke_cluster"
         OR resource.type="gce_subnetwork")
        AND NOT logName:"logs/cloudaudit.googleapis.com"
      EOT

      exclusions = local.noise_exclusions
    }

    # VPC flow logs. Separate from the application archive because they are the one source
    # whose volume can change by an order of magnitude without any code changing — a single
    # training job that starts streaming a dataset will do it — and mixing them in makes that
    # invisible in the bill.
    flow-logs = {
      description    = "VPC flow logs. Sampled at source; see _envcommon/vpc.hcl."
      destination    = "storage"
      retention_days = 400

      bucket = {
        name           = "${include.root.locals.prefix}-flow-logs"
        location       = include.root.locals.state_location
        encryption_key = dependency.kms.outputs.crypto_key_ids["logs"]

        lifecycle_rules = [
          { age = 30, action = "SetStorageClass", storage_class = "COLDLINE" },
        ]
      }

      filter = <<-EOT
        logName:"logs/compute.googleapis.com%2Fvpc_flows"
      EOT
    }
  }

  # The _Default sink in every project writes a second copy of everything above into that
  # project's own log bucket. Disabling it is what stops each project paying for storage of
  # logs this unit is already keeping centrally.
  #
  # Not disabled outright: 30 days of local retention is what makes `gcloud logging read` in
  # a project work during an incident, before anyone has opened BigQuery.
  default_sink_retention_days = 30

  labels = include.root.locals.common_labels
}
