# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# The CI cluster is an artifact authority, not a general workload cluster. Google-managed
# system images remain covered by the managed system policy; the only third-party images
# exempted from the deny-all rule are the exact reviewed ARC controller and runner digests.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "common_projects" {
  config_path = "../../../1-org/common-projects"
  mock_outputs = {
    project_ids     = { ci = "mc-common-ci" }
    project_numbers = { ci = "000000000001" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "arc_gke" {
  config_path = "../arc-gke"
  mock_outputs = {
    cluster_name = "mc-ci-arc"
    location     = "us-central1"
    project_id   = "mc-common-ci"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../1-org/kms-binauthz"
  mock_outputs = {
    key_ring_name = "projects/mock/locations/us-central1/keyRings/mock-binauthz"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  module_version = "v0.2.0"
}

terraform {
  source = "${include.root.locals.module_source_base}//binauthz?ref=${local.module_version}"
}

inputs = {
  project_id        = dependency.common_projects.outputs.project_ids["ci"]
  project_number    = dependency.common_projects.outputs.project_numbers["ci"]
  cluster           = "${dependency.arc_gke.outputs.location}.${dependency.arc_gke.outputs.cluster_name}"
  attestor_key_ring = dependency.kms.outputs.key_ring_name

  global_policy_evaluation_mode = "ENABLE"
  default_admission_rule = {
    evaluation_mode         = "ALWAYS_DENY"
    enforcement_mode        = "ENFORCED_BLOCK_AND_AUDIT_LOG"
    require_attestations_by = []
  }

  exempt_images = [
    "ghcr.io/actions/actions-runner:2.336.0@sha256:0cfdcc701ce933c6d243c6b0b2da767366dc9f2e99961d4c3754b0b78084cdda",
    "ghcr.io/actions/gha-runner-scale-set-controller:0.14.2@sha256:1b4c7f62e971ab259a4b8798e48e2adaad4af747f45990f474ea5feefa03531d",
  ]

  attestors            = {}
  attestor_signers     = {}
  attestor_verifiers   = {}
  cluster_admission_rules = {}
  labels = merge(include.root.locals.common_labels, {
    environment = "ci"
    authority   = "artifact-release"
  })
}
