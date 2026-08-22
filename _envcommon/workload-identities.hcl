# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Keyless workload identities shared by the environment's GKE capacity domains.
# Cloud permissions remain resource-scoped and are deliberately not granted here.

locals {
  root        = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars    = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  environment = local.env_vars.locals.environment

  module_version = "v0.4.0"
}

terraform {
  source = "${local.root.locals.module_source_base}//workload_identity?ref=${local.module_version}"
}

inputs = {
  pool                     = null
  oidc_providers           = {}
  federated_principal_sets = {}

  service_accounts = {
    preprocessing = {
      account_id    = "preprocessing"
      display_name  = "${local.environment} preprocessing"
      description   = "Keyless identity for the governed CPU preprocessing capacity domain."
      project_roles = []
    }
    training_h100 = {
      account_id    = "training-h100"
      display_name  = "${local.environment} H100 training"
      description   = "Keyless identity for the governed H100 training capacity domain."
      project_roles = []
    }
    training_b200 = {
      account_id    = "training-b200"
      display_name  = "${local.environment} B200 training"
      description   = "Keyless identity for the governed B200 training capacity domain."
      project_roles = []
    }
    holdout_evaluator = {
      account_id    = "holdout-evaluator"
      display_name  = "${local.environment} holdout evaluator"
      description   = "Keyless identity for isolated held-out evaluation."
      project_roles = []
    }
  }
}
