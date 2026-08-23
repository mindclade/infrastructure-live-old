# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Private developer workstation, reachable only through IAP TCP forwarding.
#
# It exists for a reason the laptop fleet cannot satisfy. `remote-execution-base` in the
# monorepo is gated `optionalAttrs pkgs.stdenv.hostPlatform.isLinux`, so an aarch64-darwin
# laptop cannot build the Nix package the CI runner image extends. This is the x86_64-linux
# host that can. The second reason is operational: tmux runs on the instance and the SSH
# tunnel is disposable, so a dropped local link no longer kills a two-hour build.
#
# ONE INSTANCE, ONE UNIT, deliberately. A `for_each` over developers would put every
# workstation in one state file, so revoking one person's access would hold a plan over
# everybody else's running machine.
#
# WHY THIS UNIT DOES NOT CREATE ITS OWN FIREWALL RULE.
# `mc-development-platform` is a Shared VPC SERVICE project; the network lives in
# `mc-development-net`. The module's `google_compute_firewall` is created in `var.project_id`,
# which here is the service project, so its own rule would be created against a network that
# project does not own and the apply would fail naming the network rather than the ownership.
# `create_iap_ssh_firewall_rule = false` therefore hands the rule to the host project, and
# `3-networks/development/firewall-baseline` implements the module's `required_firewall_rule`
# contract against the exact `network_tag` pinned below. Both halves must move together — a tag
# renamed here without the firewall rule is an instance that passes every IAM check and then
# times out at connect.
#
# WHY THE CACHE GRANTS ARE NOT HERE.
# The module emits `required_cache_grants` rather than creating them. The buckets belong to
# `5-workloads/ci/nix-binary-cache` and `5-workloads/ci/bazel-remote-cache`, which already expose
# `reader_members`/`writer_members`. Two Terraform states each believing they own the same bucket
# binding is how removing one revokes access the other still claims — and the reverse dependency
# (a ci unit reading this unit's service-account email) would close a cycle with the bucket-name
# dependencies below. Applying those grants is a separate reviewed change in the ci units.
#
# WHAT IS NOT PROVEN YET. Two connected paths this unit depends on and cannot assert:
#   - `3-networks/development/firewall-baseline` denies egress by default at priority 65000 and
#     allows only intra-VPC, `restricted.googleapis.com`, and the metadata server. The module's
#     startup script runs `apt-get` and fetches the Nix installer over the open internet, so it
#     cannot complete until a reviewed named-destination egress rule or an internal package
#     mirror exists. Widening `deny-egress-default` is not that change.
#   - `5-workloads/development/vpc-sc-perimeter` restricts `storage.googleapis.com` and the two
#     caches live in `mc-common-ci`, outside it. See that unit's egress section: the perimeter is
#     in explicit dry-run, so the reads are logged rather than denied today and will start failing
#     the moment it enforces.

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

  # Zone `-b` matches the GPU zone convention in account.hcl. The data disk is ZONAL, so this
  # choice is permanent for the life of the disk: moving the instance to another zone means
  # snapshotting and restoring the Nix store, not editing this line.
  zone = "${include.root.locals.region}-b"

  # The environment's node subnet. A dedicated subnet would be cleaner, but a new subnet cannot
  # be resized once created and one VM does not justify permanently reserving a range.
  subnetwork   = dependency.vpc.outputs.subnet_self_links[local.environment]["nodes"]
  kms_key_name = dependency.kms.outputs.crypto_key_ids["workstation"]

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
