# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "folders" {
  config_path = "../folders"
  mock_outputs = {
    folder_ids = { common = "folders/000000000000" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals { module_version = "v0.4.0" }
terraform {
  source = "${include.root.locals.module_source_base}//project_factory?ref=${local.module_version}"
}

inputs = {
  billing_account = include.root.locals.billing_account
  folder_id       = dependency.folders.outputs.folder_ids["common"]
  projects = {
    logging = {
      project_id = "${include.root.locals.prefix}-common-logging"
      name       = "Mindclade central logging"
      services = [
        "bigquery.googleapis.com",
        "logging.googleapis.com",
        "monitoring.googleapis.com",
        "pubsub.googleapis.com",
        "storage.googleapis.com",
      ]
      lien = true
    }
    security = {
      project_id = "${include.root.locals.prefix}-common-security"
      name       = "Mindclade security operations"
      services = [
        "accesscontextmanager.googleapis.com",
        "binaryauthorization.googleapis.com",
        "cloudkms.googleapis.com",
        "containeranalysis.googleapis.com",
        "securitycenter.googleapis.com",
        "secretmanager.googleapis.com",
      ]
      lien = true
    }
    billing = {
      project_id = "${include.root.locals.prefix}-common-billing"
      name       = "Mindclade billing export"
      services = [
        "bigquery.googleapis.com",
        "billingbudgets.googleapis.com",
      ]
      lien = true
    }
    dns = {
      project_id = "${include.root.locals.prefix}-common-dns"
      name       = "Mindclade authoritative DNS"
      services = [
        "certificatemanager.googleapis.com",
        "dns.googleapis.com",
        "monitoring.googleapis.com",
      ]
      lien = true
    }
    ci = {
      project_id = "${include.root.locals.prefix}-common-ci"
      name       = "Mindclade CI and supply-chain identities"
      services = [
        "artifactregistry.googleapis.com",
        "binaryauthorization.googleapis.com",
        "compute.googleapis.com",
        "container.googleapis.com",
        "containeranalysis.googleapis.com",
        "containerscanning.googleapis.com",
        "iam.googleapis.com",
        "iamcredentials.googleapis.com",
        "logging.googleapis.com",
        "monitoring.googleapis.com",
        "secretmanager.googleapis.com",
        "serviceusage.googleapis.com",
        "storage.googleapis.com",
      ]
      lien = true
    }
  }
  deletion_policy = "PREVENT"

  # Monthly USD budget for this project set.
  #
  # The common projects were the only spending projects in the estate with no budget at all,
  # while every workload project in 4-projects carries one. `ci` is why that gap mattered: it
  # holds the ARC cluster, the artifact registry, and both build caches, so it is the one common
  # project whose bill moves with load rather than sitting flat — and nothing was watching it.
  #
  # THIS IS A SET BUDGET, NOT A ci BUDGET. project_factory creates one google_billing_budget
  # whose filter lists every project it made, so this covers logging, security, billing, dns and
  # ci together. That is what the interface offers; a per-project figure would need a per-project
  # budget input on the module. 2000 is sized from ci dominating the set — the ARC system node
  # pool alone is roughly 840/month at its three-node floor — with the rest close to flat.
  # Re-baseline it here when 5-workloads/ci/arc-gke's machine-type decision is taken, rather than
  # by silencing the alert it produces.
  #
  # Alerts, never a cap. The module attaches thresholds at 50/80/100% of current spend and 100%
  # of forecast, and none of them stop anything. A cap here would take out the artifact registry
  # and both caches mid-release, and the first symptom would be a build failing on a 403 from
  # Cloud Storage rather than anything that names a budget.
  budget_amount = 2000

  labels = merge(include.root.locals.common_labels, {
    environment = "global"
    shared      = "true"
    criticality = "critical"
  })
}
