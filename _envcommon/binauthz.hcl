# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# Shared Binary Authorization defaults.
#
# This is the control that makes everything the build pipeline does actually matter. Signing
# an image and generating an SBOM changes nothing on its own — a cluster that will run any
# image gains nothing from the signature existing. This is where the signature becomes a
# precondition for the pod starting.

locals {
  root         = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config("${get_repo_root()}/account.hcl")

  environment    = local.env_vars.locals.environment
  module_version = "v0.1.1"
}

terraform {
  source = "${local.root.locals.module_source_base}//binauthz?ref=${local.module_version}"
}

inputs = {
  # DENY by default. Every exception is a named namespace below, and each one is a decision
  # somebody made rather than a gap somebody left.
  default_admission_rule = {
    evaluation_mode  = "REQUIRE_ATTESTATION"
    enforcement_mode = local.environment == "production" ? "ENFORCED_BLOCK_AND_AUDIT_LOG" : "DRYRUN_AUDIT_LOG_ONLY"
    require_attestations_by = local.environment == "production" ? [
      "build-attestor",
      "vuln-scan-attestor",
      "biosecurity-review-attestor",
      ] : [
      "build-attestor",
    ]
  }

  # Google's own system images. Without this exemption the cluster cannot start kube-proxy
  # and the node never becomes ready — a failure that looks like a networking problem.
  global_policy_evaluation_mode = "ENABLE"

  exempt_images = [
    "gcr.io/google-containers/*",
    "k8s.gcr.io/**",
    "registry.k8s.io/**",
    "gke.gcr.io/**",
  ]

  attestors = {
    build-attestor = {
      description       = "The build pipeline produced this image."
      kms_protection    = "HSM"
      kms_key_algorithm = "RSA_SIGN_PKCS1_4096_SHA512"
    }
    vuln-scan-attestor = {
      description       = "Artifact Analysis found no critical or high vulnerability."
      kms_protection    = "HSM"
      kms_key_algorithm = "RSA_SIGN_PKCS1_4096_SHA512"
    }
    biosecurity-review-attestor = {
      description       = "A human on @biosecurity reviewed this model artifact. Production only, never automated."
      kms_protection    = "HSM"
      kms_key_algorithm = "RSA_SIGN_PKCS1_4096_SHA512"
    }
  }

  labels = local.root.locals.common_labels
}
