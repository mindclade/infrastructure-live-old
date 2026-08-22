# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Shared regional Certificate Manager contract. Each environment instantiates the same stable
# resource names in its own platform project; SANs and authorization domains come from the
# canonical DNS portfolio so the certificate and private-route contracts cannot drift.

locals {
  root           = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars       = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  environment    = local.env_vars.locals.environment
  inventory      = jsondecode(file("${get_repo_root()}/contracts/dns-domain-inventory.json"))
  hostnames      = local.inventory.environment_naming.hostnames[local.environment]
  names          = local.inventory.certificate_policy.certificate_names
  module_version = "v0.4.0"

  # A regional DNS authorization covers exactly one certificate domain. Keep the key
  # deterministic because it also identifies the generated CNAME resource in state.
  dns_authorizations = merge([
    for plane, domains in local.hostnames : {
      for domain in domains :
      "${plane}-${replace(domain, ".", "-")}" => {
        plane  = plane
        domain = domain
        name   = "auth-${replace(domain, ".", "-")}"
      }
    }
  ]...)
}

terraform {
  source = "${local.root.locals.module_source_base}//certificate_manager?ref=${local.module_version}"
}
