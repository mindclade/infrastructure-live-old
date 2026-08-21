# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

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
  module_version = "v0.4.0"

  # Terraform's Binary Authorization resource has no Kubernetes-namespace-rule interface.
  # Upstream GitOps control-plane images therefore use a reviewed exact-digest contract rather
  # than a nonmatching cluster rule or a namespace-wide ALWAYS_ALLOW policy.
  argocd_exception_contract = jsondecode(file("${get_repo_root()}/contracts/argocd-image-exceptions.json"))
  argocd_exception_images = [
    for exception in local.argocd_exception_contract.exceptions : exception.image
    if contains(exception.scope.environments, local.environment)
  ]
}

terraform {
  source = "${local.root.locals.module_source_base}//binauthz?ref=${local.module_version}"
}

inputs = {
  # Deny by default. Development audits the rule; staging and production enforce it so staging
  # supplies real admission evidence before production approval.
  default_admission_rule = {
    evaluation_mode  = "REQUIRE_ATTESTATION"
    enforcement_mode = local.environment == "development" ? "DRYRUN_AUDIT_LOG_ONLY" : "ENFORCED_BLOCK_AND_AUDIT_LOG"
    # The protected deployment signer verifies independent ARC build and qualification
    # attestations before it issues deployment-attestor. Requiring build-attestor directly in
    # production would let the builder satisfy admission without the independent gate.
    require_attestations_by = local.environment == "production" ? [
      "deployment-attestor",
      ] : [
      "build-attestor",
    ]
  }

  # Google's managed system-image policy is enabled separately. User-configured exemptions are
  # restricted to the reviewed upstream Argo catalog and only exist in staging/production.
  global_policy_evaluation_mode = "ENABLE"
  exempt_images                 = local.argocd_exception_images

  attestors = {
    build-attestor = {
      description       = "The authoritative ARC builder produced and published this image."
      kms_protection    = "HSM"
      kms_key_algorithm = "RSA_SIGN_PKCS1_4096_SHA512"
    }
    qualification-attestor = {
      description       = "Independent ARC qualification, security, and numerical gates passed."
      kms_protection    = "HSM"
      kms_key_algorithm = "RSA_SIGN_PKCS1_4096_SHA512"
    }
    deployment-attestor = {
      description       = "The protected GitHub release signer verified build and qualification evidence and authorized deployment."
      kms_protection    = "HSM"
      kms_key_algorithm = "RSA_SIGN_PKCS1_4096_SHA512"
    }
    biosecurity-review-attestor = {
      description       = "A human on @biosecurity reviewed a restricted biological model artifact; never a global platform-image prerequisite."
      kms_protection    = "HSM"
      kms_key_algorithm = "RSA_SIGN_PKCS1_4096_SHA512"
    }
  }

  labels = local.root.locals.common_labels
}
