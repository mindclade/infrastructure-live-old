# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Cloud KMS key ring for org-scoped consumers that belong to no environment.
#
# Was one unit holding all three environments' rings PLUS this one, in a single state file —
# which meant a development key change and a production key change were the same plan and the
# same lock. The per-environment rings now live at 2-environments/<env>/kms, and the Binary
# Authorization ring at 1-org/kms-binauthz. See docs/module-interface-contract.md.
#
# What is left here is the `global` ring: log sinks and the SCC findings export, which are org
# resources and have no environment to belong to.
#
# Key rings cannot be deleted, and ring names cannot be reused for a different purpose.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "common_projects" {
  config_path = "../common-projects"
  mock_outputs = {
    project_numbers = { ci = "000000000001" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

terraform {
  source = "${include.root.locals.module_source_base}//kms?ref=${local.module_version}"
}

locals {
  module_version = "v0.4.0"
}

inputs = {
  project_id = include.root.locals.seed_project_id
  location   = include.root.locals.region

  key_ring_name = "${include.root.locals.prefix}-global"

  keys = {
    # Log sinks, the audit archive, and access transparency. Longer rotation than the
    # per-environment keys because a log written under an old version must stay readable for
    # its full seven-year retention, and every extra version is one more thing that must
    # never be destroyed.
    logs = {
      rotation_period_seconds = 31536000 # 365 days
      protection_level        = "HSM"
    }
    ci_secrets = {
      rotation_period_seconds = 7776000 # 90 days
      protection_level        = "HSM"
    }
    ci_artifacts = {
      rotation_period_seconds = 7776000 # 90 days
      protection_level        = "HSM"
    }
  }

  encrypter_decrypters = {
    ci_artifacts = [
      "serviceAccount:service-${dependency.common_projects.outputs.project_numbers["ci"]}@gs-project-accounts.iam.gserviceaccount.com",
    ]
  }

  labels = include.root.locals.common_labels
}
