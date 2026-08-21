# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Shared defaults for a 4-projects/<env>/<domain> unit.
#
# One project per (domain, environment), and — since the split recorded in
# docs/module-interface-contract.md — one UNIT per project. This file used to fan a single unit out
# over all three environments with a `for` expression; that put three environments in one
# state, so a production project could not be applied without holding a plan over development
# and staging as well.
#
# What this file still owns is the part that genuinely is common: the module pin, the billing
# account, the services every domain project enables, and the labels. What varies by
# environment now varies by directory, which is where `env.hcl` can reach it.
#
# What lives in a domain project: that domain's DATA and its domain-specific managed
# services. What does not: compute. The GKE cluster is one per environment in the shared
# platform project (see _envcommon/shared-projects.hcl), and it reaches these projects as a
# Workload Identity principal rather than by sharing a project boundary with them.

locals {
  root         = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  prefix = local.account_vars.locals.prefix

  # v0.1.2 is the first tag carrying `shared_vpc_host_project_id` and
  # `remove_default_service_account`. Both are controls these units already declared and the
  # module could not accept — see docs/module-interface-contract.md. Cut the tag in the monorepo
  # before applying anything here; the pin is deliberate and must not be relaxed to a branch.
  module_version = "v0.1.2"

  # Enabled in every domain project, in every environment. A service missing in one
  # environment means the first deploy there fails on an API that was never turned on, which
  # is a bad thing to learn during a promotion.
  base_services = [
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudkms.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ]
}

terraform {
  source = "${local.root.locals.module_source_base}//project?ref=${local.module_version}"
}

inputs = {
  billing_account_id = local.account_vars.locals.billing_account

  # `region` is deliberately NOT passed. A project is a global resource; the module creates
  # nothing regional, and passing a region it does not declare is one of the interface
  # mismatches this split existed to remove.
  #
  # `deletion_policy` is likewise not passed: the module hardcodes PREVENT on the project, its
  # services and its budget. Deleting one of these projects deletes a training corpus or an
  # evaluation set rather than a rebuildable cache, so the behaviour is not a knob.

  labels = local.root.locals.common_labels
}
