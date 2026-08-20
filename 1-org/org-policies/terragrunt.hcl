# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# The full constraint set. bootstrap applies only the subset needed to build safely.
#
# The split is deliberate. bootstrap runs before anything exists and must not be able to lock
# itself out, so it applies the constraints that make a mistake unrecoverable — no service
# account keys, no public buckets, no external IPs — and stops there. Everything that
# constrains how workloads are BUILT belongs here, where it is applied by a pipeline and
# reviewed as a PR.
#
# THIS UNIT MUST NOT REDECLARE A CONSTRAINT bootstrap ALREADY OWNS. Two configurations
# managing one policy each read the other's value as drift and revert it on every apply,
# which produces no error and no stable state. The list bootstrap owns is in
# the former bootstrap governance owner; every constraint below is absent from it.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//org_policy?ref=${local.module_version}"
}

locals {
  module_version = "v0.1.1"
}

# The sandbox folder gets one constraint relaxed, so this unit needs its id.
dependency "folders" {
  config_path = "../folders"

  mock_outputs = {
    folder_ids = {
      partners = "folders/000000000000"
      sandbox  = "folders/000000000001"
    }
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
}

inputs = {
  parent = "organizations/${include.root.locals.org_id}"

  # ---------------------------------------------------------------------------------------
  # Boolean constraints
  # ---------------------------------------------------------------------------------------
  boolean_policies = {
    # Shielded VM: secure boot, vTPM, integrity monitoring. GKE sets this per node pool
    # anyway; enforcing it org-wide is what covers the VM somebody creates by hand.
    "compute.requireShieldedVm" = true

    # IP forwarding turns any VM into a router, which is how a workload reaches a subnet the
    # firewall says it cannot. Nothing here needs it; a NAT gateway is a managed service.
    "compute.vmCanIpForward" = false

    # Removing a lien on a Shared VPC host project is the step before deleting it out from
    # under every service project attached to it.
    "compute.restrictXpnProjectLienRemoval" = true

    # Serial-port output can contain secrets echoed by a startup script. Bootstrap already
    # denies interactive serial access; this denies the log.
    "compute.disableSerialPortLogging" = true

    # Guest attributes are a metadata channel readable by anything on the instance, which
    # makes them a convenient exfiltration path out of a locked-down VM.
    "compute.disableGuestAttributesAccess" = true

    # Nested virtualisation is already denied by bootstrap. Not repeated here.

    # GKE node diagnostic data can be uploaded to Google support with cluster contents in it.
    # Fine as a deliberate act during a support case; not fine as a default.
    "container.restrictNoncompliantDiagnosticDataAccess" = true

    # No IPv6 anywhere. Every firewall rule, VPC-SC perimeter, and NAT config in 3-networks
    # is written for IPv4 only — a dual-stack subnet would have an egress path none of them
    # describe, which is a hole nobody would see in a diff.
    "compute.disableAllIpv6" = true

    # A Cloud Run or Cloud Functions workload with no VPC connector egresses straight to the
    # internet, outside the NAT in 3-networks and outside every VPC-SC perimeter.
    "cloudfunctions.requireVPCConnector" = true
  }

  # ---------------------------------------------------------------------------------------
  # List constraints
  # ---------------------------------------------------------------------------------------
  list_policies = {
    # CMEK, not Google-managed keys, on the services that hold model weights, training data,
    # and credentials. This is the constraint that makes 1-org/kms load-bearing rather than
    # decorative: without it, a bucket created without an `encryption_key` is silently
    # Google-managed and looks identical in the console.
    "gcp.restrictNonCmekServices" = {
      allowed_values = []
      denied_values = [
        "storage.googleapis.com",
        "bigquery.googleapis.com",
        "secretmanager.googleapis.com",
        "container.googleapis.com",
        "artifactregistry.googleapis.com",
      ]
    }

    # Where a CMEK may live. Without this, a project can satisfy the constraint above with a
    # key in a project nobody governs — which is CMEK in name and Google-managed in effect.
    "gcp.restrictCmekCryptoKeyProjects" = {
      allowed_values = ["projects/${include.root.locals.seed_project_id}"]
      denied_values  = []
    }

    # WIF issuers. The single most important list constraint in this estate: it stops a
    # workload identity pool being created that trusts an issuer we do not control. Without
    # it, someone with project-level IAM can federate an arbitrary OIDC provider and mint
    # credentials the audit log records as legitimate.
    "iam.workloadIdentityPoolProviders" = {
      allowed_values = [
        "https://token.actions.githubusercontent.com",
        "https://agent.buildkite.com",
      ]
      denied_values = []
    }

    # Shared VPC hosts. A project that can become a host project can offer subnets to
    # anything that asks, so the allowlist is scoped to this organization — a project in
    # someone else's org cannot host a network our service projects attach to.
    "compute.restrictSharedVpcHostProjects" = {
      allowed_values = ["under:organizations/${include.root.locals.org_id}"]
      denied_values  = []
    }

    # External load balancers. Internal ones are unrestricted; an external one publishes a
    # service to the internet, and every such service here goes through the ingress path in
    # 5-workloads rather than being created ad hoc.
    "compute.restrictLoadBalancerCreationForTypes" = {
      allowed_values = [
        "INTERNAL_TCP_UDP",
        "INTERNAL_HTTP_HTTPS",
        "INTERNAL_MANAGED",
      ]
      denied_values = []
    }

    # Protocol forwarding to an external address is a way to expose a VM without creating
    # anything the load-balancer constraint above would catch.
    "compute.restrictProtocolForwardingCreationForTypes" = {
      allowed_values = ["INTERNAL"]
      denied_values  = []
    }

    # VPC peering leaves the perimeter without leaving the console. Restricting it to our own
    # org means a peering to a partner's network is a policy exception somebody signs off.
    "compute.restrictVpcPeering" = {
      allowed_values = ["under:organizations/${include.root.locals.org_id}"]
      denied_values  = []
    }

    # TLS floor for Google API access. 1.2 is the floor rather than 1.3 because some Google
    # client libraries still negotiate 1.2 and the failure mode is an opaque handshake error.
    "gcp.restrictTLSVersion" = {
      allowed_values = []
      denied_values  = ["TLS_VERSION_1", "TLS_VERSION_1_1"]
    }
  }

  # ---------------------------------------------------------------------------------------
  # Folder-scoped exceptions
  # ---------------------------------------------------------------------------------------
  # Sandbox relaxes exactly one constraint. The reasoning is that people run experiments
  # somewhere regardless, and the alternative to a sandbox with external IPs is `development`
  # with external IPs — where the relaxation would be permanent and invisible.
  #
  # Nothing else is loosened, and nothing in sandbox is reachable from a production network:
  # it has its own folder, and 3-networks peers no VPC into it.
  folder_overrides = {
    "${dependency.folders.outputs.folder_ids["sandbox"]}" = {
      "compute.vmExternalIpAccess" = {
        # Reset rather than allow_all: reset restores the org default of deny, then the rule
        # below re-permits. Writing allow_all directly would inherit nothing and silently
        # drop any future org-level tightening.
        deny_all = false
        reason   = "Experiments need reachable endpoints. Isolated folder, no peering, 2000 budget cap."
      }
    }
  }

  labels = include.root.locals.common_labels
}
