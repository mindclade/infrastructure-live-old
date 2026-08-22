# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/gateway-certificates.hcl"
  expose         = true
  merge_strategy = "deep"
}

dependency "shared" {
  config_path                             = "../../../2-environments/production/shared-projects"
  mock_outputs                            = { project_ids = { platform = "mc-production-platform" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "common_projects" {
  config_path                             = "../../../1-org/common-projects"
  mock_outputs                            = { project_ids = { dns = "mc-common-dns" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "ai_zone" {
  config_path                             = "../../../3-networks/shared/public-zones/mindclade-ai"
  mock_outputs                            = { zone_names = { mindclade-ai = "mindclade-ai" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "dev_zone" {
  config_path                             = "../../../3-networks/shared/public-zones/mindclade-dev"
  mock_outputs                            = { zone_names = { mindclade-dev = "mindclade-dev" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "studio_zone" {
  config_path                             = "../../../3-networks/shared/public-zones/mindclade-studio"
  mock_outputs                            = { zone_names = { mindclade-studio = "mindclade-studio" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id     = dependency.shared.outputs.project_ids["platform"]
  location       = include.root.locals.region
  dns_project_id = dependency.common_projects.outputs.project_ids["dns"]
  dns_authorizations = {
    for key, authorization in include.envcommon.locals.dns_authorizations : key => {
      name   = authorization.name
      domain = authorization.domain
      managed_zone = {
        ai        = dependency.ai_zone.outputs.zone_names["mindclade-ai"]
        developer = dependency.dev_zone.outputs.zone_names["mindclade-dev"]
        studio    = dependency.studio_zone.outputs.zone_names["mindclade-studio"]
      }[authorization.plane]
    }
  }
  certificates = {
    for plane, domains in include.envcommon.locals.hostnames : plane => {
      name    = include.envcommon.locals.names[plane]
      domains = domains
      authorization_keys = [
        for key, authorization in include.envcommon.locals.dns_authorizations :
        key if authorization.plane == plane
      ]
    }
  }
  labels = merge(include.root.locals.common_labels, { scope = "gateway-tls" })
}
