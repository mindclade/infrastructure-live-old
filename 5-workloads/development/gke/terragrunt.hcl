# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# WORKED REFERENCE UNIT — copy this shape when filling in the stubs.
#
# It demonstrates the four things every real unit needs:
#   1. include "root"      — remote state, providers, labels
#   2. include "envcommon" — shared defaults for this component type
#   3. dependency blocks   — typed inputs from other units, with mock outputs so `plan`
#                            works before the dependency has ever been applied
#   4. inputs              — only what genuinely differs from the envcommon default

include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/gke.hcl"

  # expose = true makes the included config readable here as include.envcommon.*, which is
  # how a unit reads a shared local rather than duplicating it.
  expose = true

  # deep, not shallow. A shallow merge replaces whole maps, so setting one label here would
  # silently drop every label from _envcommon.
  merge_strategy = "deep"
}

# ---------------------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------------------
# These create the apply ordering. `terragrunt run --all apply` builds the graph from them,
# so a missing dependency block is not a missing input — it is a race.
dependency "shared" {
  config_path = "../../../2-environments/development/shared-projects"

  mock_outputs = {
    project_ids = {
      platform = "mc-development-platform"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "vpc" {
  config_path = "../../../3-networks/development/shared-vpc-host"

  # Mock outputs let `plan` run before this dependency has ever been applied, which is what
  # makes plan-on-PR work for a new environment. allowed_command_names is the important
  # half: without it, mocks would also be used during `apply` and the cluster would be built
  # against a fake network id.
  #
  # EVERY OUTPUT HERE IS A MAP KEYED BY ENVIRONMENT. 3-networks is one unit covering all
  # three environments — see _envcommon/vpc.hcl for why — so a consumer indexes what it
  # needs rather than receiving a scalar. Indexing with the wrong key is a plan-time error;
  # a scalar would have been a production VPC quietly shared with development.
  mock_outputs = {
    network_self_link    = { development = "projects/mock/global/networks/mock-development-vpc" }
    subnetwork_names     = { development = "mock-development-nodes" }
    pods_range_names     = { development = "mock-development-pods" }
    services_range_names = { development = "mock-development-services" }
    host_project_ids     = { development = "mc-development-net" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../2-environments/development/kms"

  # Also keyed by environment, and for the same reason: one keyring per environment is what
  # makes "revoke development's access to production data" a single IAM change.
  mock_outputs = {
    crypto_key_ids = {
      gke = "projects/mock/locations/europe-west4/keyRings/mock-development/cryptoKeys/gke"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

# ---------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------
# Only what differs from _envcommon/gke.hcl. Anything repeated from there is a value that
# will eventually diverge in one environment and not the others.
inputs = {
  # `include.envcommon.locals.environment` rather than a literal "development" — that local
  # is derived from env.hcl, so this unit cannot index a different environment than the
  # directory it lives in. Copying this file to ../../staging/gke needs no edit here.
  project_id = dependency.shared.outputs.project_ids["platform"]

  network         = dependency.vpc.outputs.network_self_link[include.envcommon.locals.environment]
  subnetwork      = dependency.vpc.outputs.subnetwork_names[include.envcommon.locals.environment]
  host_project_id = dependency.vpc.outputs.host_project_ids[include.envcommon.locals.environment]

  ip_range_pods     = dependency.vpc.outputs.pods_range_names[include.envcommon.locals.environment]
  ip_range_services = dependency.vpc.outputs.services_range_names[include.envcommon.locals.environment]

  database_encryption_key = dependency.kms.outputs.crypto_key_ids["gke"]

  # Small default pool. Real workloads run on the taint-guarded pools in ../nodepools.
  initial_node_count = 1
  min_node_count     = 1
  max_node_count     = 5
  machine_type       = "e2-standard-4"
}
