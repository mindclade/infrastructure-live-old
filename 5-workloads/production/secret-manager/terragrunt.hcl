# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Workload secrets, replicated per residency requirement.
#
# Terraform creates the CONTAINERS, never the values — the same rule bootstrap follows, for
# the same reason: a secret value in Terraform state is a secret in the state bucket, in
# every plan artifact, and in every local .terraform directory.
#
# Workloads read these through Workload Identity, so no pod holds a credential and nothing is
# mounted from a file. The chain terminates at a Kubernetes service account token GKE mints
# per pod, which cannot be exfiltrated usefully because it expires in an hour and is bound to
# one service account in one namespace.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//secret_manager?ref=${local.module_version}"
}

locals {
  module_version = "v0.4.0"
  env_vars       = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env            = local.env_vars.locals.environment
}

dependency "shared" {
  config_path = "../../../2-environments/production/shared-projects"

  # BOTH maps. A mock that omits an output the unit reads does not degrade gracefully — the
  # reference fails with "This object does not have an attribute named project_numbers",
  # which reads like the dependency does not produce it rather than like the mock is
  # incomplete. project_numbers is read below for the Workload Identity member string.
  mock_outputs = {
    project_ids     = { platform = "mc-production-platform" }
    project_numbers = { platform = "000000000000" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms" {
  config_path = "../../../2-environments/production/kms"

  mock_outputs = {
    crypto_key_ids = {
      secrets = "projects/mock/locations/us-central1/keyRings/mock-production/cryptoKeys/secrets"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "kms_dr" {
  config_path = "../../../2-environments/production/kms-dr"

  mock_outputs = {
    crypto_key_ids = {
      secrets = "projects/mock/locations/us-east4/keyRings/mock-production-dr/cryptoKeys/secrets"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  project_id  = dependency.shared.outputs.project_ids["platform"]
  environment = local.env

  # The NUMBER, not the id. A Workload Identity direct principal addresses the project by
  # number while the pool inside it is addressed by id — the same project named two ways in
  # one member string. Substituting one for the other yields a member IAM accepts and no
  # workload matches, so the apply succeeds and every secret read is denied.
  project_number = dependency.shared.outputs.project_numbers["platform"]

  # ---------------------------------------------------------------------------------------
  # Replication
  # ---------------------------------------------------------------------------------------
  # USER-MANAGED, not automatic.
  #
  # Automatic replication puts a copy in every Google region, which is convenient and
  # violates gcp.resourceLocations — the org policy in bootstrap restricts where data may
  # live, and a secret is data. Naming the replica explicitly is also what makes CMEK
  # possible: automatic replication cannot use a customer key.
  replication = {
    user_managed = [
      {
        location     = include.root.locals.region
        kms_key_name = dependency.kms.outputs.crypto_key_ids["secrets"]
      },
      {
        location     = include.root.locals.dr_region
        kms_key_name = dependency.kms_dr.outputs.crypto_key_ids["secrets"]
      },
    ]
  }

  secrets = {
    # ------------------------------------------------------------------------------------
    # Platform
    # ------------------------------------------------------------------------------------
    argocd-gitops-app-pem = {
      description = "GitHub App key ArgoCD uses to read the gitops repo. See the gitops bootstrap and Argo CD runbook."
      accessors   = ["argocd"]

      # Rotated on the schedule in bootstrap/docs/credential-rotation.md. The annotation is
      # what a rotation job reads to know which secrets it owns — a secret with no rotation
      # period is one nobody will ever rotate.
      rotation_period = "7776000s" # 90 days
    }

    # ------------------------------------------------------------------------------------
    # Workload
    # ------------------------------------------------------------------------------------
    # Named per workload rather than one shared blob, so that a grant is scoped to the
    # workload that needs it. A single `app-secrets` secret means every accessor holds
    # everything in it.
    runtime-gateway-signing-key = {
      description     = "Signs response envelopes from the runtime gateway."
      accessors       = ["runtime-gateway"]
      rotation_period = "2592000s" # 30 days
    }

    data-ingestion-partner-token = {
      description     = "Bearer token for the partner ingestion feed."
      accessors       = ["data-ingestion-worker"]
      rotation_period = "2592000s"
    }

    # ------------------------------------------------------------------------------------
    # Browser plane
    # ------------------------------------------------------------------------------------
    # The session cookie's AEAD keys. TWO SECRETS, not one, and both live at once.
    #
    # The BFF accepts a cookie sealed with either and issues with the newer. That overlap is
    # the whole reason there are two: rotate a single key and every user in the system is
    # logged out at the same instant, which presents as a total outage and is the failure
    # mode this shape exists to prevent.
    #
    # THE OVERLAP MUST EXCEED TWICE THE SESSION TTL. With a five-minute TTL a 30-day rotation
    # is enormous margin and costs nothing. Retrofitting rotation onto a single-key deployment
    # means either an outage or a fleet-wide invalidation, which is why both ship on day one
    # rather than the second being added when rotation is first needed.
    #
    # What these keys can do if leaked is bounded, and that bound is the point: a forged
    # cookie is INERT without a matching IAP assertion for the same subject, because the
    # cookie is a cache of an authorization decision rather than a bearer of identity. That
    # property is a direct consequence of keeping IAP, and it does not survive dropping it.
    studio-session-key-a = {
      description     = "AEAD key A for __Host-mc_session. Live alongside key B; overlap must exceed twice the 5-minute session TTL."
      accessors       = ["studio-bff"]
      rotation_period = "2592000s" # 30 days
    }

    studio-session-key-b = {
      description     = "AEAD key B for __Host-mc_session. See key A — both are live, deliberately."
      accessors       = ["studio-bff"]
      rotation_period = "2592000s"
    }

    # NO iap-oauth-client secret, and its absence is a finding rather than an omission.
    #
    # The design assumed a CUSTOM OAuth client — provisioned here, with an INTERNAL audience,
    # its secret referenced by GCPBackendPolicy. That is no longer possible for anyone: Google
    # deprecated the IAP OAuth Admin APIs on 22 Jan 2025 and permanently shut them down on
    # 19 March 2026. A Terraform module for it was written for this estate and deleted, because
    # it could only ever have failed at apply.
    #
    # IAP now uses the Google-managed client, so there is no secret to hold. What the custom
    # client would have bought — an internal-audience consent screen — is replaced by scoping
    # `roles/iap.httpsResourceAccessor` to the organization's group. See the note in the
    # monorepo's planes/studio/base/backendpolicy.yaml.

    # ------------------------------------------------------------------------------------
    # Developer plane
    # ------------------------------------------------------------------------------------
    # Athens' git credential. ONE system holds this, which is the operational argument for
    # putting a module proxy in front of the vanity endpoint at all — the alternative is the
    # same credential on every laptop and every CI runner.
    goproxy-netrc = {
      description     = "netrc granting Athens read access to the monorepo. The only copy of this credential in the estate."
      accessors       = ["goproxy"]
      rotation_period = "7776000s" # 90 days
    }
  }

  # Workload Identity bindings: <k8s-namespace>/<k8s-service-account> to the accessor names
  # above. Declaring them here rather than in the manifests keeps "who can read this secret"
  # answerable from one file instead of from a search across gitops/rendered.
  workload_identity_bindings = {
    argocd                = { namespace = "argocd", service_account = "argocd-repo-server" }
    runtime-gateway       = { namespace = "serving-runtime-gateway", service_account = "runtime-gateway" }
    data-ingestion-worker = { namespace = "data-ingestion-worker", service_account = "ingestion-worker" }

    # Plane namespaces, created with the Gateway in the monorepo's
    # infra/kubernetes/platform/gateway. The namespace names here are the ones carrying the
    # `plane` labels the listeners select on — they are not free-form.
    studio-bff = { namespace = "studio", service_account = "studio-bff" }
    goproxy    = { namespace = "dev", service_account = "goproxy" }
  }

  # Alert when a secret is read by a principal outside its accessor list. DATA_READ auditing
  # on secretmanager is on org-wide (bootstrap), which is what makes this detectable at all —
  # this turns the log line into a page.
  alert_on_unexpected_access = true

  labels = include.root.locals.common_labels
}
