# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# VPC Service Controls perimeter and ingress/egress rules.
#
# The control that makes a stolen credential insufficient. IAM answers "may this identity
# read the bucket"; VPC-SC answers "may this bucket be read from there at all". An exfiltrated
# service account token used from outside the perimeter is refused even though the IAM check
# passes, which is the one failure mode nothing else in the estate covers.
#
# THREE THINGS THAT CATCH PEOPLE, all of them expensive to learn during an incident:
#
#   PROPAGATION IS SLOW. An apply returns and denials continue for up to 30 minutes. The
#   temptation is to apply again, which does nothing except make the timeline harder to read.
#
#   DRY RUN FIRST, ALWAYS. `use_explicit_dry_run_spec` below logs what WOULD be blocked
#   without blocking it. A perimeter shipped straight to enforced takes out whatever nobody
#   thought of, and the symptom is every API call in the environment failing at once with a
#   message that names the perimeter and not the missing rule.
#
#   A PERIMETER PROTECTS PROJECTS, NOT NETWORKS. Adding a project is what brings it inside;
#   a firewall rule has nothing to do with it.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//network?ref=${local.module_version}"
}

locals {
  module_version = "v0.1.0"
  env_vars       = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env            = local.env_vars.locals.environment
}

# Every project inside the perimeter. A missing dependency here is not a missing input — it
# is a project left outside the perimeter, which is invisible and is the whole failure this
# unit exists to prevent.
dependency "shared" {
  config_path = "../../../2-environments/development/shared-projects"

  mock_outputs = {
    project_numbers = { net = "000000000001", ops = "000000000002", platform = "000000000003" }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "research" {
  config_path = "../../../4-projects/development/research"

  mock_outputs = {
    project_number = "000000000004"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "data" {
  config_path = "../../../4-projects/development/data"

  mock_outputs = {
    project_number = "000000000005"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "serving" {
  config_path = "../../../4-projects/development/serving"

  mock_outputs = {
    project_number = "000000000006"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "observability" {
  config_path                             = "../../../4-projects/development/observability"
  mock_outputs                            = { project_number = "000000000007" }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "security" {
  config_path                             = "../../../4-projects/development/security"
  mock_outputs                            = { project_number = "000000000008" }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "automation" {
  config_path = "../../../1-org/automation-iam"
  mock_outputs = { supply_chain_service_accounts = {
    builder   = "sa-artifact-builder@mc-common-ci.iam.gserviceaccount.com"
    qualifier = "sa-artifact-qualifier@mc-common-ci.iam.gserviceaccount.com"
    signer    = "sa-artifact-signer@mc-common-ci.iam.gserviceaccount.com"
    promoter  = "sa-artifact-promoter@mc-common-ci.iam.gserviceaccount.com"
  } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

dependency "control_plane" {
  config_path = "../../shared/control-plane-identities"
  mock_outputs = { service_accounts = {
    gitops_render   = "sa-gitops-render@mc-common-security.iam.gserviceaccount.com"
    gitops_verifier = "sa-gitops-verifier@mc-common-security.iam.gserviceaccount.com"
  } }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  org_id      = include.root.locals.org_id
  policy_name = "${include.root.locals.prefix}-access-policy"

  perimeter = {
    name  = "${include.root.locals.prefix}_${local.env}"
    title = "${local.env} perimeter"

    # ------------------------------------------------------------------------------------
    # DRY RUN
    # ------------------------------------------------------------------------------------
    # Development enforces. This is the environment where a perimeter mistake should surface,
    # and enforcing here is what makes staging and production's dry-run periods meaningful —
    # they are rehearsing something already known to work.
    #
    # Staging and production set this to true until their violation logs are clean. See the
    # header.
    use_explicit_dry_run_spec = true

    resources = [
      "projects/${dependency.shared.outputs.project_numbers["ops"]}",
      "projects/${dependency.shared.outputs.project_numbers["platform"]}",
      "projects/${dependency.research.outputs.project_number}",
      "projects/${dependency.data.outputs.project_number}",
      "projects/${dependency.serving.outputs.project_number}",
      "projects/${dependency.observability.outputs.project_number}",
      "projects/${dependency.security.outputs.project_number}",
    ]

    # The host project is deliberately OUTSIDE the perimeter. It holds no data — only the
    # network — and including it means every network API call from CI has to cross the
    # boundary, which is a large ingress rule protecting nothing.

    # ------------------------------------------------------------------------------------
    # Restricted services
    # ------------------------------------------------------------------------------------
    # The services that hold data worth exfiltrating. Restricting everything is tempting and
    # wrong: each additional service is another set of ingress rules to maintain, and a
    # perimeter that is too painful to maintain gets an exception that swallows it.
    restricted_services = [
      "storage.googleapis.com",
      "bigquery.googleapis.com",
      "secretmanager.googleapis.com",
      "artifactregistry.googleapis.com",
      "aiplatform.googleapis.com",
      "container.googleapis.com",
    ]

    # Which restricted services are reachable from INSIDE the perimeter over the private
    # endpoint. Without this, a workload inside the perimeter cannot call the services the
    # perimeter is protecting — which is a working perimeter and a broken environment.
    vpc_accessible_services = {
      enable_restriction = true
      allowed_services   = ["RESTRICTED-SERVICES"]
    }
  }

  # ---------------------------------------------------------------------------------------
  # Ingress
  # ---------------------------------------------------------------------------------------
  # Who may reach in from outside. Each rule names an identity AND a service — a rule that
  # names only an identity grants that identity the whole perimeter.
  ingress_policies = [
    {
      # Terraform's own apply identity. Without this, the pipeline that manages the perimeter
      # cannot manage anything inside it — including removing the perimeter, which is the
      # lockout this rule exists to prevent.
      title = "terraform-apply"
      from = {
        identities = [
          "serviceAccount:${include.root.locals.account_vars.locals.infrastructure_live_service_accounts.foundation}",
          "serviceAccount:${include.root.locals.account_vars.locals.infrastructure_live_service_accounts.development}",
        ]
        identity_type        = null
        source_access_levels = ["*"]
      }
      to = {
        resources = ["*"]
        operations = {
          "storage.googleapis.com"          = { methods = ["*"] }
          "bigquery.googleapis.com"         = { methods = ["*"] }
          "secretmanager.googleapis.com"    = { methods = ["*"] }
          "artifactregistry.googleapis.com" = { methods = ["*"] }
          "aiplatform.googleapis.com"       = { methods = ["*"] }
          "container.googleapis.com"        = { methods = ["*"] }
        }
      }
    },
    {
      # The read-only plan identity. Scoped to read methods so a plan cannot mutate anything
      # inside the perimeter even if the service account were granted more by mistake.
      title = "terraform-plan-readonly"
      from = {
        identities           = ["serviceAccount:${include.root.locals.account_vars.locals.infrastructure_live_service_accounts.plan}"]
        source_access_levels = ["*"]
      }
      to = {
        resources = ["*"]
        operations = {
          "storage.googleapis.com"          = { methods = ["google.storage.buckets.get", "google.storage.buckets.list", "google.storage.objects.get", "google.storage.objects.list"] }
          "bigquery.googleapis.com"         = { methods = ["*Get*", "*List*"] }
          "secretmanager.googleapis.com"    = { methods = ["*Get*", "*List*"] }
          "artifactregistry.googleapis.com" = { methods = ["*Get*", "*List*"] }
          "aiplatform.googleapis.com"       = { methods = ["*Get*", "*List*"] }
          "container.googleapis.com"        = { methods = ["*Get*", "*List*"] }
        }
      }
    },
    {
      title = "artifact-supply-chain"
      from = {
        identities           = [for email in values(dependency.automation.outputs.supply_chain_service_accounts) : "serviceAccount:${email}"]
        source_access_levels = ["*"]
      }
      to = {
        resources = ["projects/${dependency.shared.outputs.project_numbers["platform"]}"]
        operations = {
          "artifactregistry.googleapis.com" = { methods = ["*"] }
        }
      }
    },
    {
      title = "gitops-artifact-verifier"
      from = {
        identities           = ["serviceAccount:${dependency.control_plane.outputs.service_accounts["gitops_verifier"]}"]
        source_access_levels = ["*"]
      }
      to = {
        resources = ["projects/${dependency.shared.outputs.project_numbers["platform"]}"]
        operations = {
          "artifactregistry.googleapis.com" = { methods = ["*Get*", "*List*", "*Download*"] }
        }
      }
    },
  ]

  # ---------------------------------------------------------------------------------------
  # Egress
  # ---------------------------------------------------------------------------------------
  # What may be reached OUTSIDE the perimeter from inside it. This is the direction that
  # matters for exfiltration, and the list is deliberately almost empty.
  # Environment registries are inside their own perimeter. Promotion is performed by the
  # external, IAM-scoped promoter through ingress, so no broad perimeter egress is required.
  egress_policies = []

  # No access levels based on IP range. An IP-based access level is a perimeter that a VPN
  # defeats; identity is the only attribute here that means anything.
  access_levels = {}
}
