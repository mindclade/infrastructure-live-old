# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Held-out evaluation data. IAM DENY policy on every training SA.
#
# THE MOST IMPORTANT BUCKET IN THE ESTATE, and the one whose failure is silent.
#
# A benchmark number is only meaningful if the model has never seen the evaluation set. If
# the holdout leaks into training, every number the organization reports afterwards is wrong,
# nothing breaks, no alert fires, and the leak is undetectable after the fact — you cannot
# look at a trained model and tell whether it saw a particular shard.
#
# So this bucket is defended twice, in two different systems, because either alone fails
# open in a way nobody would notice:
#
#   1. AN IAM DENY POLICY, here. Deny beats allow unconditionally in GCP — a training
#      identity granted storage.objectViewer at the project level still cannot read this
#      bucket. That is the property an allow-based model cannot give: with allow-only, the
#      protection is the ABSENCE of a grant, and absence is one careless `roles/viewer` away
#      from ceasing to exist.
#
#   2. A GATEKEEPER CONSTRAINT, in gitops/policy/constraints/deny-holdout-bucket-mount.yaml,
#      which stops a pod mounting it at all. That catches the case where a workload runs as
#      an identity nobody thought to add to the deny below.
#
# Changing anything here needs @biosecurity and @security review. That is enforced by the
# protected-paths ruleset in github-config, not by this comment.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/gcs-bucket.hcl"
  expose         = true
  merge_strategy = "deep"
}

dependency "research" {
  config_path = "../../../../4-projects/staging/research"

  mock_outputs = {
    project_id = "mc-staging-research"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "workload_identities" {
  config_path = "../../workload-identities"

  mock_outputs = {
    service_accounts = {
      preprocessing     = { email = "preprocessing@mc-staging-research.iam.gserviceaccount.com" }
      training_h100     = { email = "training-h100@mc-staging-research.iam.gserviceaccount.com" }
      training_b200     = { email = "training-b200@mc-staging-research.iam.gserviceaccount.com" }
      holdout_evaluator = { email = "holdout-evaluator@mc-staging-research.iam.gserviceaccount.com" }
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

locals {
  env = include.envcommon.locals.environment
}

inputs = {
  project_id = dependency.research.outputs.project_id

  buckets = {
    holdout = {
      name = "${include.root.locals.prefix}-${local.env}-holdout"

      # No lifecycle transition to a colder class, against the envcommon default. A holdout
      # set is read at every evaluation and the retrieval cost of Coldline would exceed the
      # storage saving — and a slow evaluation is one people are tempted to skip.
      lifecycle_rules = []

      # Retention lock. The holdout has to outlive the models evaluated against it, or a
      # published number cannot be reproduced.
      retention_days = 3650

      # Object versioning plus soft delete even in staging. Overwriting a holdout shard
      # is as damaging as leaking it: the number is still wrong, just differently.
      versioning                    = true
      soft_delete_retention_seconds = 604800
    }
  }

  bucket_iam_members = {
    holdout_evaluator = {
      bucket_key = "holdout"
      role       = "roles/storage.objectViewer"
      member     = "serviceAccount:${dependency.workload_identities.outputs.service_accounts["holdout_evaluator"].email}"
    }
  }

  # ---------------------------------------------------------------------------------------
  # The deny policy
  # ---------------------------------------------------------------------------------------
  # IAM Deny is evaluated BEFORE any allow and cannot be overridden by one, including by an
  # org admin's own grant. That asymmetry is the entire point — it is the only construct in
  # GCP where the protection does not depend on nobody having granted something.
  #
  # Scoped to the storage read permissions rather than to a role: a role can be replaced with
  # a custom one carrying the same permissions, and the deny would no longer match.
  deny_policies = {
    holdout-no-training-read = {
      display_name = "Training identities may not read the holdout set"

      rules = [
        {
          # Every identity that runs training or preprocessing. Evaluation is deliberately
          # ABSENT — it is the one workload that is supposed to read this bucket, and it is
          # the whole reason the bucket exists.
          #
          # Adding an identity here is safe. Removing one is the change to look at twice: the
          # failure mode of a missing entry is not an error, it is a benchmark that quietly
          # stops meaning anything.
          # Consume the dedicated workload-identity unit's real service-account outputs. This
          # dependency is both a typed identity contract and an apply-order edge: the deny can
          # never be planned against a fictional account name inferred from the project id.
          denied_principals = [
            "principal://iam.googleapis.com/projects/-/serviceAccounts/${dependency.workload_identities.outputs.service_accounts["preprocessing"].email}",
            "principal://iam.googleapis.com/projects/-/serviceAccounts/${dependency.workload_identities.outputs.service_accounts["training_h100"].email}",
            "principal://iam.googleapis.com/projects/-/serviceAccounts/${dependency.workload_identities.outputs.service_accounts["training_b200"].email}",
          ]

          denied_permissions = [
            "storage.googleapis.com/objects.get",
            "storage.googleapis.com/objects.list",
            "storage.googleapis.com/objects.getIamPolicy",
          ]

          # No exception principals. An exception here would be a training identity permitted
          # to read the holdout, which is the exact thing being prevented — if one genuinely
          # needs the data, it is not a holdout any more and belongs in the lakehouse.
          exception_principals = []
        },
      ]
    }
  }

  labels = merge(include.root.locals.common_labels, {
    data-class = "holdout"
    # Read by the Gatekeeper constraint in gitops. The two controls are independent, and this
    # label is what lets the second one find the bucket without a hardcoded name.
    "mindclade-dev-holdout" = "true"
  })
}
