# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}
include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/private-service-dns.hcl"
  expose         = true
  merge_strategy = "deep"
}
dependency "vpc" {
  config_path = "../shared-vpc-host"
  mock_outputs = {
    host_project_ids  = { staging = "mc-staging-net" }
    network_self_link = { staging = "projects/mc-staging-net/global/networks/staging" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}
dependency "gateway_vip" {
  config_path                             = "../gateway-vip"
  mock_outputs                            = { addresses = { staging = "10.32.33.10" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}
inputs = {
  project_id = dependency.vpc.outputs.host_project_ids[include.envcommon.locals.environment]
  zones = {
    mindclade-ai-private = {
      dns_name   = "mindclade.ai."
      visibility = "private"
      networks   = [dependency.vpc.outputs.network_self_link[include.envcommon.locals.environment]]
      records = { for hostname in include.envcommon.locals.hostnames["ai"] :
        replace(hostname, ".", "-") => {
          name    = trimsuffix(hostname, ".mindclade.ai"), type = "A", ttl = 300
          rrdatas = [dependency.gateway_vip.outputs.addresses[include.envcommon.locals.environment]]
        }
      }
    }
    mindclade-dev-private = {
      dns_name   = "mindclade.dev."
      visibility = "private"
      networks   = [dependency.vpc.outputs.network_self_link[include.envcommon.locals.environment]]
      records = { for hostname in include.envcommon.locals.hostnames["developer"] :
        replace(hostname, ".", "-") => {
          name    = trimsuffix(hostname, ".mindclade.dev"), type = "A", ttl = 300
          rrdatas = [dependency.gateway_vip.outputs.addresses[include.envcommon.locals.environment]]
        }
      }
    }
    mindclade-studio-private = {
      dns_name   = "mindclade.studio."
      visibility = "private"
      networks   = [dependency.vpc.outputs.network_self_link[include.envcommon.locals.environment]]
      records = { for hostname in include.envcommon.locals.hostnames["studio"] :
        replace(hostname, ".", "-") => {
          name    = hostname == "mindclade.studio" ? "@" : trimsuffix(hostname, ".mindclade.studio"), type = "A", ttl = 300
          rrdatas = [dependency.gateway_vip.outputs.addresses[include.envcommon.locals.environment]]
        }
      }
    }
  }
  labels = merge(include.root.locals.common_labels, { scope = "private-service-dns" })
}
