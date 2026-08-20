# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Organization- and folder-scoped Essential Contacts. `bootstrap` intentionally owns none;
# this unit is the single Terraform state owner for the complete contact routing baseline.
# Folder routing is still useful because an organization-level contact
# receives everything for everywhere. A GPU quota warning in `development` and a suspension
# notice on `production` arrive in the same inbox with the same weight, and within a month
# the filter rule someone wrote to cope means neither is read.
#
# The essentialcontacts.allowedContactDomains policy in the adjacent org-policies unit
# restricts every address here to @mindclade.com, so a personal address cannot be subscribed.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//essential_contacts?ref=${local.module_version}"
}

locals {
  module_version = "v0.1.1"
}

dependency "folders" {
  config_path = "../folders"

  mock_outputs = {
    folder_ids = {
      partners = "folders/000000000000"
      sandbox  = "folders/000000000001"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  # Group addresses only, every one of them. A contact pointing at a person stops working the
  # day they leave, and nobody notices until a notification is missed — which is exactly the
  # notification that mattered. The domain org policy rejects non-Mindclade addresses.
  contacts = {
    # ------------------------------------------------------------------------------------
    # Organization-wide recovery, security, billing, and legal routing
    # ------------------------------------------------------------------------------------
    "organizations/${include.root.locals.org_id}" = [
      {
        email         = "security@${include.root.locals.domain}"
        subscriptions = ["SECURITY", "TECHNICAL_INCIDENTS"]
      },
      {
        email         = "platform@${include.root.locals.domain}"
        subscriptions = ["TECHNICAL", "SUSPENSION"]
      },
      {
        email         = "billing@${include.root.locals.domain}"
        subscriptions = ["BILLING"]
      },
      {
        email         = "legal@${include.root.locals.domain}"
        subscriptions = ["LEGAL"]
      },
    ]

    # ------------------------------------------------------------------------------------
    # Partner tenancy
    # ------------------------------------------------------------------------------------
    # A partner folder suspension is a contractual event, not just an operational one, so
    # legal is subscribed alongside platform. This is the one folder where that is true.
    "${dependency.folders.outputs.folder_ids["partners"]}" = [
      {
        email         = "platform@${include.root.locals.domain}"
        subscriptions = ["TECHNICAL", "TECHNICAL_INCIDENTS", "SUSPENSION"]
      },
      {
        email         = "legal@${include.root.locals.domain}"
        subscriptions = ["SUSPENSION", "LEGAL"]
      },
    ]

    # ------------------------------------------------------------------------------------
    # Sandbox
    # ------------------------------------------------------------------------------------
    # Technical only, and no security subscription: sandbox findings are expected and routing
    # them to @security trains people to ignore mail from @security.
    "${dependency.folders.outputs.folder_ids["sandbox"]}" = [
      {
        email         = "platform@${include.root.locals.domain}"
        subscriptions = ["TECHNICAL"]
      },
    ]
  }
}
