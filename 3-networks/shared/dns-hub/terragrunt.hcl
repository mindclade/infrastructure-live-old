# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

locals { module_version = "4d5c0105295bf4a01b770fb75f6a8db5c22c8f79" }
terraform {
  source = "${include.root.locals.module_source_base}//dns?ref=${local.module_version}"
}

dependency "common_projects" {
  config_path                             = "../../../1-org/common-projects"
  mock_outputs                            = { project_ids = { dns = "mc-common-dns" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "development_vpc" {
  config_path                             = "../../development/shared-vpc-host"
  mock_outputs                            = { network_self_link = { development = "projects/mock/global/networks/development" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}
dependency "staging_vpc" {
  config_path                             = "../../staging/shared-vpc-host"
  mock_outputs                            = { network_self_link = { staging = "projects/mock/global/networks/staging" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}
dependency "production_vpc" {
  config_path                             = "../../production/shared-vpc-host"
  mock_outputs                            = { network_self_link = { production = "projects/mock/global/networks/production" } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id = dependency.common_projects.outputs.project_ids["dns"]
  zones = {
    gcp-internal = {
      domain     = "gcp.mindclade.com."
      visibility = "private"
      networks = [
        dependency.development_vpc.outputs.network_self_link["development"],
        dependency.staging_vpc.outputs.network_self_link["staging"],
        dependency.production_vpc.outputs.network_self_link["production"],
      ]
      records = {}
    }

    # VPC-SC workloads resolve Google APIs through the restricted VIP. Google documents a
    # private googleapis.com zone with an A record for restricted.googleapis.com and a
    # wildcard CNAME; no PSC forwarding rule is involved in this path.
    restricted-googleapis = {
      domain     = "googleapis.com."
      visibility = "private"
      networks = [
        dependency.development_vpc.outputs.network_self_link["development"],
        dependency.staging_vpc.outputs.network_self_link["staging"],
        dependency.production_vpc.outputs.network_self_link["production"],
      ]
      records = {
        restricted-a = {
          name    = "restricted"
          type    = "A"
          ttl     = 300
          rrdatas = ["199.36.153.4", "199.36.153.5", "199.36.153.6", "199.36.153.7"]
        }
        wildcard-cname = {
          name    = "*"
          type    = "CNAME"
          ttl     = 300
          rrdatas = ["restricted.googleapis.com."]
        }
      }
    }

    restricted-pkg-dev = {
      domain     = "pkg.dev."
      visibility = "private"
      networks = [
        dependency.development_vpc.outputs.network_self_link["development"],
        dependency.staging_vpc.outputs.network_self_link["staging"],
        dependency.production_vpc.outputs.network_self_link["production"],
      ]
      records = {
        wildcard-cname = {
          name    = "*"
          type    = "CNAME"
          ttl     = 300
          rrdatas = ["restricted.googleapis.com."]
        }
      }
    }

    restricted-gcr-io = {
      domain     = "gcr.io."
      visibility = "private"
      networks = [
        dependency.development_vpc.outputs.network_self_link["development"],
        dependency.staging_vpc.outputs.network_self_link["staging"],
        dependency.production_vpc.outputs.network_self_link["production"],
      ]
      records = {
        wildcard-cname = {
          name    = "*"
          type    = "CNAME"
          ttl     = 300
          rrdatas = ["restricted.googleapis.com."]
        }
      }
    }
  }
  labels = merge(include.root.locals.common_labels, { scope = "private" })
}
