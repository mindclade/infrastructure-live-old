# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

locals {
  module_version = "v0.4.0"
  inventory      = jsondecode(file("${get_repo_root()}/contracts/dns-domain-inventory.json"))
  domain         = one([for domain in local.inventory.domains : domain if domain.domain == "mindclade.ai"])
  records = {
    for record in local.domain.records :
    "${replace(record.name, "@", "apex")}-${lower(record.type)}" => {
      name    = record.name
      type    = record.type
      ttl     = record.ttl
      rrdatas = record.type == "TXT" ? [for value in record.rrdatas : jsonencode(value)] : record.rrdatas
    }
  }
}
terraform {
  source = "${include.root.locals.module_source_base}//dns?ref=${local.module_version}"
}

dependency "common_projects" {
  config_path                             = "../../../../1-org/common-projects"
  mock_outputs                            = { project_ids = { dns = "mc-common-dns" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id = dependency.common_projects.outputs.project_ids["dns"]
  zones = {
    mindclade-ai = {
      dns_name   = "mindclade.ai."
      visibility = "public"
      dnssec     = true
      public_record_allowlist = local.domain.public_record_allowlist
      records    = local.records
    }
  }
  labels = merge(include.root.locals.common_labels, {
    scope  = "public"
    domain = "mindclade-ai"
  })
}
