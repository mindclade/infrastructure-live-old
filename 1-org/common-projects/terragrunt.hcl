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

locals { module_version = "v0.1.1" }
terraform {
  source = "${include.root.locals.module_source_base}//project?ref=${local.module_version}"
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
      ]
      lien = true
    }
  }
  deletion_policy = "PREVENT"
  labels = merge(include.root.locals.common_labels, {
    environment = "global"
    shared      = "true"
    criticality = "critical"
  })
}
