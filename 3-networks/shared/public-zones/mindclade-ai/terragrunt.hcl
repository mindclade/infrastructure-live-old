# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

locals { module_version = "v0.4.0" }
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
    mindclade_ai = {
      domain              = "mindclade.ai."
      visibility          = "public"
      dnssec              = true
      deletion_protection = true
      records = {
        "@-mx" = {
          name    = "@"
          type    = "MX"
          ttl     = 3600
          rrdatas = ["0 ."]
        }
        "@-txt" = {
          name    = "@"
          type    = "TXT"
          ttl     = 3600
          rrdatas = ["\"v=spf1 -all\""]
        }
        "_dmarc-txt" = {
          name    = "_dmarc"
          type    = "TXT"
          ttl     = 3600
          rrdatas = ["\"v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s\""]
        }
      }
    }
  }
  labels = merge(include.root.locals.common_labels, {
    scope  = "public"
    domain = "mindclade-ai"
  })
}
