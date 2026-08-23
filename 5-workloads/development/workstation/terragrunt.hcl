# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Private x86_64-linux developer workstation, reachable only through IAP TCP forwarding.
#
# The source design is complete: an immutable NixOS image contains Nix, Git, tmux, and the
# idle-shutdown timer, so first boot performs no public package or installer fetch. GitHub may
# publish only a content-addressed raw-disk object. Terraform creates the CMEK-protected Compute
# Image and passes its exact self-link plus embedded-contract digest to this module.
#
# ACTIVATION IS BLOCKED until bootstrap contract 2.0.0, workflow contract v5.0.0, and Terraform
# modules v0.4.0 are published and applied through their protected paths; the raw-disk object and
# Compute Image then need connected first-boot, idle-shutdown, rollback, and VPC-SC cache tests.
# `contracts/workstation-egress.json` is the machine-readable authority for those gates.
#
# The IAP firewall rule remains in the Shared VPC host project. Cache grants remain in their
# bucket-owning CI states. One instance remains one unit so revoking one operator never holds a
# shared workstation state hostage.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "shared" {
  config_path = "../../../2-environments/development/shared-projects"

  mock_outputs = {
    project_ids = { platform = "mc-development-platform" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

# `subnet_self_links` rather than `subnetwork_names`, because the module takes a fully qualified
# subnetwork and a bare name would resolve against the wrong project in a Shared VPC.
dependency "vpc" {
  config_path = "../../../3-networks/development/shared-vpc-host"

  mock_outputs = {
    subnet_self_links = {
      development = {
        nodes = "https://www.googleapis.com/compute/v1/projects/mc-development-net/regions/us-central1/subnetworks/nodes"
      }
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

# CMEK is required by the module for both disks. The `workstation` key is added to the
# development ring by `2-environments/development/kms`, together with the
# `cryptoKeyEncrypterDecrypter` grant the Compute Engine service agent needs before either disk
# can be created — the module names that prerequisite in `required_grants` and cannot create it.
dependency "kms" {
  config_path = "../../../2-environments/development/kms"

  mock_outputs = {
    crypto_key_ids = {
      workstation = "projects/mc-bootstrap-seed/locations/us-central1/keyRings/mc-development/cryptoKeys/workstation"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "image" {
  config_path = "../workstation-image"

  mock_outputs = {
    image = {
      self_link = "https://www.googleapis.com/compute/v1/projects/mc-development-platform/global/images/mc-development-workstation-0123456789ab"
    }
    source_contract = {
      image_contract_sha256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "nix_cache" {
  config_path = "../../ci/nix-binary-cache"

  mock_outputs = {
    bucket = { name = "mc-common-ci-nix-cache" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "bazel_cache" {
  config_path = "../../ci/bazel-remote-cache"

  mock_outputs = {
    bucket = { name = "mc-common-ci-bazel-cache" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  module_version = "v0.4.0"
  environment    = include.root.locals.environment
}

terraform {
  source = "${include.root.locals.module_source_base}//workstation?ref=${local.module_version}"
}

inputs = {
  project_id = dependency.shared.outputs.project_ids["platform"]
  name       = "${include.root.locals.prefix}-${local.environment}-workstation"
  region     = include.root.locals.region

  # Zone `-b` matches the GPU zone convention in account.hcl. The data disk is zonal, so moving
  # the instance requires snapshotting and restoring the workspace/Bazel data disk.
  zone = "${include.root.locals.region}-b"

  # The environment's node subnet. A dedicated subnet would be cleaner, but a new subnet cannot
  # be resized once created and one VM does not justify permanently reserving a range.
  subnetwork            = dependency.vpc.outputs.subnet_self_links[local.environment]["nodes"]
  kms_key_name          = dependency.kms.outputs.crypto_key_ids["workstation"]
  image                 = dependency.image.outputs.image.self_link
  image_contract_sha256 = dependency.image.outputs.source_contract.image_contract_sha256

  service_account_id = "sa-${local.environment}-workstation"

  # A group, not a list of people. Membership then changes in Cloud Identity rather than in a
  # Terraform apply, which is what keeps offboarding off the critical path of a plan. The module
  # refuses service-account, domain, and wildcard principals here on purpose: IAP SSH is a human
  # path, and a service account holding tunnel access is an unattended door into a box that can
  # reach the caches. The group must exist before apply, exactly as `gke-security-groups@` must.
  operator_principals = ["group:developer-platform@${include.root.locals.domain}"]

  # 16 vCPU x86_64. Arm is refused by the module because the `.#gpu` shell is x86_64-linux only,
  # so an Arm workstation could not enter the shell it exists to run. Stated here rather than
  # left to the module default because it is the single line that sets the hourly cost, and the
  # idle-shutdown default (60 minutes) is what keeps that cost bounded.
  machine_type = "c2d-standard-16"

  # See the header. The rule is owned by the host project in
  # 3-networks/development/firewall-baseline; this tag is the join between the two.
  create_iap_ssh_firewall_rule = false
  network_tag                  = "${local.environment}-workstation-iap-ssh"

  nix_cache_bucket_name   = dependency.nix_cache.outputs.bucket.name
  bazel_cache_bucket_name = dependency.bazel_cache.outputs.bucket.name

  environment         = local.environment
  owner               = "developer-platform"
  data_classification = "internal"

  # `extra_project_roles` is deliberately left empty. The module's floor is logWriter and
  # metricWriter; anything resembling signing, attestation, publication, or token minting is
  # refused outright, and that refusal is the boundary the ARC runner-group split also holds.
  labels = merge(include.root.locals.common_labels, {
    authority = "terraform"
  })
}
