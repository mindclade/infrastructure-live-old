# IAP access handoff — staging

This directory intentionally contains **no Terragrunt unit**.

The GKE Gateway controller owns the generated Compute backend services, while the
`gitops` repository owns IAP enablement through `GCPBackendPolicy` resources. A Terraform
unit that copies generated backend-service names back into live configuration creates a
backward Ring-2-to-Ring-1 dependency and can silently bind the wrong resource.

The staging browser plane remains disabled until all of the following are true:

1. its workload images are released and pinned by digest;
2. the GitOps package contains `GCPBackendPolicy` with
   `spec.default.iap.enabled: true`;
3. access is granted through a reviewed, stable IAM design—preferably a dedicated project
   or a module consuming stable Gateway outputs, never manually copied generated names;
4. the access principal is an IdP-managed group, not an individual or
   `allAuthenticatedUsers`;
5. the resulting IAP policy is tested from both an authorized and an unauthorized identity.

Google-managed IAP OAuth clients are the default for internal browser access. Custom OAuth
credentials are used only when external users or custom branding require them, and their
secrets stay outside Git.

See `docs/gitops-handoff.md` and the GitOps rendering/provenance gates before activation.
