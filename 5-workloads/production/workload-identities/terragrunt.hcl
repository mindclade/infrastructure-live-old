# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/workload-identities.hcl"
  merge_strategy = "deep"
}

dependency "research" {
  config_path = "../../../4-projects/production/research"
  mock_outputs = {
    project_id     = "mc-production-research"
    project_number = "100000000013"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "shared" {
  config_path = "../../../2-environments/production/shared-projects"
  mock_outputs = {
    project_ids = { platform = "mc-production-platform" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id     = dependency.research.outputs.project_id
  project_number = dependency.research.outputs.project_number

  gke_ksa_bindings = {
    preprocessing = {
      service_account_key = "preprocessing"
      namespace           = "mindclade-batch-cpu"
      ksa_name            = "mindclade-batch-cpu"
      gke_project_id      = dependency.shared.outputs.project_ids["platform"]
    }
    training_h100 = {
      service_account_key = "training_h100"
      namespace           = "mindclade-training-h100"
      ksa_name            = "mindclade-training-h100"
      gke_project_id      = dependency.shared.outputs.project_ids["platform"]
    }
    training_b200 = {
      service_account_key = "training_b200"
      namespace           = "mindclade-training-b200"
      ksa_name            = "mindclade-training-b200"
      gke_project_id      = dependency.shared.outputs.project_ids["platform"]
    }
    holdout_evaluator = {
      service_account_key = "holdout_evaluator"
      namespace           = "mindclade-evaluation"
      ksa_name            = "mindclade-holdout-evaluator"
      gke_project_id      = dependency.shared.outputs.project_ids["platform"]
    }
  }
}
