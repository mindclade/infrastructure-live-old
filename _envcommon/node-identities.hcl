# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Dedicated keyless VM identities consumed by the regional system and accelerator pools.
# Kubernetes workload identities are deliberately separate: node credentials must never be
# the application authorization path.

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
  gke_ksa_bindings         = {}

  service_accounts = {
    system_nodes = {
      account_id    = "sa-system-nodes"
      display_name  = "${local.environment} GKE system nodes"
      description   = "Keyless VM identity for the protected regional GKE system pool."
      project_roles = ["roles/container.defaultNodeServiceAccount"]
    }
    gpu_nodes = {
      account_id    = "sa-gpu-nodes"
      display_name  = "${local.environment} GKE accelerator nodes"
      description   = "Keyless VM identity for qualified accelerator capacity."
      project_roles = ["roles/container.defaultNodeServiceAccount"]
    }
  }
}
