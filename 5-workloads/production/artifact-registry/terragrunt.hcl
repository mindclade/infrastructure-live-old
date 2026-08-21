# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Container and language artifact repositories.
#
# One registry per environment rather than one shared registry with environment tags. The
# reason is promotion: a shared registry makes "has this image reached production" a question
# about tags, which are mutable, rather than about which repository holds the digest.
#
# Every consumer references images by DIGEST, never by tag — enforced in the gitops repo by
# verify-attestation.yml. A tag here is a human convenience and nothing depends on it.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//artifact_registry?ref=${local.module_version}"
}

locals {
  module_version = "v0.1.0"
  env_vars       = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env            = local.env_vars.locals.environment
}

dependency "shared" {
  config_path = "../../../2-environments/production/shared-projects"

  mock_outputs = {
    project_ids = { platform = "mc-production-platform" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../2-environments/production/kms"

  mock_outputs = {
    crypto_key_ids = {
      storage = "projects/mock/locations/europe-west4/keyRings/mock-production/cryptoKeys/storage"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id = dependency.shared.outputs.project_ids["platform"]
  location   = include.root.locals.region

  # CMEK on the registry. Required by the gcp.restrictNonCmekServices constraint in
  # 1-org/org-policies, which names artifactregistry — a repository created without a key
  # fails at creation rather than silently using a Google-managed one.
  encryption_key = dependency.kms.outputs.crypto_key_ids["storage"]

  repositories = {
    # ------------------------------------------------------------------------------------
    # Container images
    # ------------------------------------------------------------------------------------
    containers = {
      format      = "DOCKER"
      description = "Service and workload images. Referenced by digest everywhere."

      docker_config = {
        # Tags are mutable and this makes them not be. The reason is Binary Authorization: an
        # attestation binds to a digest, so a movable tag means an attested tag can point at
        # different bytes by the time the pod starts — which is exactly the gap attestation
        # exists to close.
        immutable_tags = true
      }

      cleanup_policies = {
        # Untagged images accumulate from every rebuilt layer and are invisible in the UI
        # unless you go looking. Thirty days is longer than any rollback window here.
        delete-untagged = {
          action          = "DELETE"
          condition_state = "UNTAGGED"
          older_than      = "2592000s"
        }

        # Keep the last twenty tagged versions per package regardless of age. A rollback
        # target that was garbage-collected is a rollback that cannot happen.
        keep-recent = {
          action               = "KEEP"
          most_recent_versions = 20
        }
      }
    }

    # ------------------------------------------------------------------------------------
    # Language packages
    # ------------------------------------------------------------------------------------
    python = {
      format      = "PYTHON"
      description = "Internal Python distributions. Not a PyPI mirror — see remote-pypi."
    }

    # ------------------------------------------------------------------------------------
    # Upstream mirrors
    # ------------------------------------------------------------------------------------
    # Remote repositories, not a pass-through. Two properties this buys:
    #
    #   A build does not fail because upstream is down or yanked a version. The mirror keeps
    #   what was already pulled.
    #
    #   Every third-party artifact that entered the estate is enumerable after the fact,
    #   which is the question asked first when an upstream package turns out to be malicious.
    remote-docker = {
      format      = "DOCKER"
      description = "Pull-through cache for docker.io. Never push here."
      mode        = "REMOTE_REPOSITORY"

      remote_config = {
        docker_repository = "DOCKER_HUB"
      }
    }

    remote-pypi = {
      format      = "PYTHON"
      description = "Pull-through cache for PyPI. Never push here."
      mode        = "REMOTE_REPOSITORY"

      remote_config = {
        python_repository = "PYPI"
      }
    }
  }

  # Vulnerability scanning on push. Its findings are part of independent qualification before
  # qualification-attestor is issued — see ../binary-authorization. Without scanning the gate has
  # nothing to assert on and every image fails admission in production.
  enable_vulnerability_scanning = true

  labels = include.root.locals.common_labels
}
