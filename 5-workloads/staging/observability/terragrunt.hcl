# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Managed Prometheus, alert policies, SLOs.
#
# Managed Prometheus itself is switched on by the cluster (`enable_managed_prometheus` in
# _envcommon/gke.hcl). What this unit adds is everything that makes the metrics useful: the
# recording rules, the alert policies, and the SLOs.
#
# The rule applied to every alert below: an alert that cannot be acted on at 03:00 is a
# dashboard, and putting it in the paging path trains people to ignore the path. Anything
# informational goes to a dashboard or a daily digest instead.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//environment_alerting?ref=${local.module_version}"
}

locals {
  module_version = "v0.4.0"
  env_vars       = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env            = local.env_vars.locals.environment
}

dependency "gke" {
  config_path = "../gke"

  mock_outputs = {
    cluster_name = "mc-staging"
    location     = "europe-west4"
    project_id   = "mc-staging-platform"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "observability" {
  config_path = "../../../4-projects/staging/observability"

  mock_outputs = {
    project_id = "mc-staging-observability"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "shared" {
  config_path = "../../../2-environments/staging/shared-projects"

  # The metrics SCOPE lives on the shared ops project — every workload project in the
  # environment writes into it, so one query spans the environment. The alert policies below
  # live in the observability project and read across that scope.
  mock_outputs = {
    project_ids = { ops = "mc-staging-ops" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id            = dependency.observability.outputs.project_id
  metrics_scope_project = dependency.shared.outputs.project_ids["ops"]
  cluster_name          = dependency.gke.outputs.cluster_name

  # ---------------------------------------------------------------------------------------
  # Notification routing
  # ---------------------------------------------------------------------------------------
  # Staging pages nobody. Every alert here lands in a channel that is read during working
  # hours, because the point of alerting in staging is to catch a bad rule before it
  # reaches an environment where it would page — not to wake anyone.
  notification_channels = {
    platform-email = {
      type  = "email"
      email = "platform@${include.root.locals.domain}"
    }
  }

  default_notification_channels = ["platform-email"]

  # ---------------------------------------------------------------------------------------
  # Alerts
  # ---------------------------------------------------------------------------------------
  alert_policies = {
    # The GPU alert, and the one that pays for this whole unit. A pool that has scaled up and
    # is sitting idle is the single largest avoidable cost in the estate, and nothing else
    # surfaces it — the nodes are healthy, the cluster is fine, and the bill arrives in a
    # month.
    gpu-nodes-idle = {
      display_name = "GPU nodes allocated with no running workload"
      severity     = "WARNING"

      condition = {
        filter          = <<-EOT
          metric.type="kubernetes.io/node/accelerator/duty_cycle"
          resource.type="k8s_node"
        EOT
        comparison      = "COMPARISON_LT"
        threshold_value = 5
        duration        = "1800s"
        aligner         = "ALIGN_MEAN"
      }

      documentation = <<-EOT
        One or more GPU nodes have been allocated with near-zero utilisation for 30 minutes.

        Usually one of:
          - A job finished and Kueue has not scaled the pool down. Check the pool's
            autoscaler events.
          - A pod is holding the node without using it — a stuck init container, or a
            workload that tolerated the GPU taint without needing a GPU.
          - Someone scaled the pool manually. min_node_count is 0 in
            _envcommon/gpu-nodepool.hcl and should have stayed there.
      EOT
    }

    # Nodes that never became ready. Distinguishes "the pool scaled up" from "the pool tried
    # to scale up", which look identical in a dashboard and completely different in a bill.
    node-provisioning-failing = {
      display_name = "Node pool cannot provision"
      severity     = "WARNING"

      condition = {
        filter          = <<-EOT
          metric.type="logging.googleapis.com/user/node_provisioning_failures"
          resource.type="k8s_cluster"
        EOT
        comparison      = "COMPARISON_GT"
        threshold_value = 0
        duration        = "900s"
        aligner         = "ALIGN_SUM"
      }

      documentation = "Usually accelerator stock in the pinned zone. See node_locations in ../nodepools/gpu-a3."
    }

    # Admission denials. Expected in staging, where binary-authorization runs DRYRUN —
    # but a spike means a workload is about to fail in production, where the same policy
    # blocks.
    admission-denials-rising = {
      display_name = "Binary Authorization or Gatekeeper denials rising"
      severity     = "WARNING"

      condition = {
        filter          = <<-EOT
          metric.type="logging.googleapis.com/user/admission_denials"
          resource.type="k8s_cluster"
        EOT
        comparison      = "COMPARISON_GT"
        threshold_value = 10
        duration        = "600s"
        aligner         = "ALIGN_SUM"
      }

      documentation = <<-EOT
        Staging runs Binary Authorization in DRYRUN, so these are denials that were
        LOGGED rather than enforced. Production enforces the same policy.

        This is the alert that gives you warning before a promotion fails.
      EOT
    }
  }

  # ---------------------------------------------------------------------------------------
  # SLOs
  # ---------------------------------------------------------------------------------------
  # Defined in staging as well as production, deliberately. An SLO written for the first
  # time against production is an SLO nobody has ever seen fire, and the first thing it
  # teaches you is that the query was wrong.
  # SLO creation is blocked until service owners supply explicit project-scoped good and
  # total metric filters. A goal without those filters is not an enforceable SLO contract.
  labels = include.root.locals.common_labels
}
