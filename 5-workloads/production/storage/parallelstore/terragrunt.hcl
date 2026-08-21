# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Parallelstore or Filestore for training scratch.
#
# The shared POSIX filesystem a distributed run needs and GCS cannot be: mmap, random writes,
# and a directory rename that is not a copy. Used for the working set of a run — the tokenised
# shards, the compiled kernels, the optimiser state that has not been checkpointed yet.
#
# NOT the checkpoint store. Checkpoints go to ../gcs-checkpoints, which survives this
# filesystem being deleted. Anything here is scratch by definition, and the module is
# configured so that is true rather than merely intended.
#
# THE COST SHAPE IS DIFFERENT FROM EVERY OTHER STORAGE UNIT. Parallelstore bills on
# PROVISIONED capacity, not used — an instance sitting empty over a weekend costs exactly the
# same as a full one. GCS habits do not transfer.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//parallelstore?ref=${local.module_version}"
}

locals {
  module_version = "v0.4.0"
  env_vars       = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env            = local.env_vars.locals.environment
}

dependency "vpc" {
  config_path = "../../../../3-networks/production/shared-vpc-host"

  mock_outputs = {
    network_self_link = { production = "projects/mock/global/networks/mock-production-vpc" }
    host_project_id   = "mc-production-research"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "psc" {
  config_path = "../../../../3-networks/shared/private-service-connect"

  # Parallelstore attaches through service networking, so the allocated range in that unit
  # has to exist first. A missing dependency here is not a missing input — it is an instance
  # creation that fails after twenty minutes with a message about peering.
  mock_outputs = {
    service_networking_ranges = { production = "mc-production-servicenetworking" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "research" {
  config_path = "../../../../4-projects/production/research"

  mock_outputs = {
    project_id = "mc-production-research"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id = dependency.research.outputs.project_id

  parallelstore = {
    scratch = {
      name = "${include.root.locals.prefix}-${local.env}-scratch"

      # Zonal, and in the SAME zone as the GPU pools in ../../nodepools. A cross-zone mount
      # adds latency to every read in the training loop, which shows up as GPUs idling rather
      # than as a storage error.
      location = include.root.locals.account_vars.locals.gpu_zone

      # 12 TiB is the minimum Parallelstore provisions. Production runs do not need more,
      # and the number to watch is not this one but whether the instance exists at all.
      capacity_gib = 12000

      # SCRATCH, not PERSISTENT. Names the intent in the API rather than only in this
      # comment, and it is the cheaper tier — appropriate because everything here is
      # reconstructible from GCS.
      deployment_type = "SCRATCH"

      network           = dependency.vpc.outputs.network_self_link[local.env]
      reserved_ip_range = dependency.psc.outputs.service_networking_ranges[local.env]

      # Import from and export to GCS on a schedule. This is what keeps "scratch is
      # disposable" true: the shards are staged in from ../gcs-lakehouse rather than being
      # the only copy.
      gcs_import = {
        source = "gs://${include.root.locals.prefix}-${local.env}-lake-features"
      }
    }
  }

  labels = merge(include.root.locals.common_labels, {
    data-class  = "scratch"
    cost-centre = "research"
    # Provisioned-capacity billing, so an idle instance is a full-price instance. The label
    # is what makes it findable in a cost report before the invoice arrives.
    billing-model = "provisioned"
  })
}
