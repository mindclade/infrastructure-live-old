# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

locals { module_version = "v0.1.1" }
terraform {
  source = "${include.root.locals.module_source_base}//folder_factory?ref=${local.module_version}"
}

inputs = {
  parent          = "organizations/${include.root.locals.org_id}"
  billing_account = include.root.locals.billing_account
  folders = {
    common = {
      display_name        = "Common"
      deletion_protection = true
    }
    networking = {
      display_name        = "Networking"
      deletion_protection = true
    }
    development = {
      display_name        = "Development"
      deletion_protection = true
    }
    staging = {
      display_name        = "Staging"
      deletion_protection = true
    }
    production = {
      display_name        = "Production"
      deletion_protection = true
    }
    partners = {
      display_name        = "Partners"
      deletion_protection = true
    }
    sandbox = {
      display_name        = "Sandbox"
      deletion_protection = false
    }
  }
  folder_budgets = {
    partners = 5000
    sandbox  = 2000
  }
}
