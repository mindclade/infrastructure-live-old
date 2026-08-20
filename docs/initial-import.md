<!-- mindclade-doc: how-to@1 -->

# Import and activate the Infrastructure Live repository

> **Audience:** Infrastructure bootstrap operators  
> **Outcome:** Import the live tree, prove its account and module contracts, and activate
> protected scopes without recreating existing cloud resources.

## Prerequisites

- the existing `mindclade/infrastructure-live` repository and `.git` history;
- `.github` workflow release `v3.0.0`, completed Ring-0 bootstrap, and applied
  `github-config` environments and variables;
- distinct plan and scope-specific apply identities with qualified negative tests;
- the exact immutable internal-monorepo module releases referenced by live units; and
- inventory and import decisions for any pre-existing Google Cloud resources.

Do not enable protected apply until account values have been generated from verified
bootstrap outputs and the target estate has been reconciled with Terraform state.

## Import and validate

1. Back up the current repository and record its default-branch commit.
2. Copy this tree into the existing checkout while preserving `.git`. Exclude `.account.env`,
   Terraform or Terragrunt caches, plans, state, credentials, and local overrides.
3. Generate the ignored account contract from the verified bootstrap checkout. The exporter
   fails closed unless the Ring-0 `platform_contract` version is exactly supported. Supply
   the immutable Cloud Identity customer ID that is already present in the organization-level
   `iam.allowedPolicyMemberDomains` policy; do not guess it from the domain name:

   ```sh
   CLOUD_IDENTITY_CUSTOMER_ID='<existing-customer-id>' \
     python3 scripts/bootstrap-account.py ../bootstrap
   ```

4. Enter the pinned shell and run structural validation:

   ```sh
   nix develop
   make validate
   ```

5. Validate immutable module interfaces against the approved internal monorepo checkout using
   the repository's module-interface script and contract.
6. Inventory existing resources one state unit at a time. Google automatically provisions a
   security baseline in newer organizations. In `1-org/org-policies`, import every existing
   baseline policy into its exact v2 address before planning; never create a similarly named
   legacy policy as a substitute:

   ```sh
   terragrunt import 'google_org_policy_policy.list["iam.allowedPolicyMemberDomains"]' \
     "organizations/${GCP_ORG_ID}/policies/iam.allowedPolicyMemberDomains"
   terragrunt import 'google_org_policy_policy.boolean["storage.uniformBucketLevelAccess"]' \
     "organizations/${GCP_ORG_ID}/policies/storage.uniformBucketLevelAccess"
   terragrunt import 'google_org_policy_policy.managed["essentialcontacts.managed.allowedContactDomains"]' \
     "organizations/${GCP_ORG_ID}/policies/essentialcontacts.managed.allowedContactDomains"
   terragrunt import 'google_org_policy_policy.managed["iam.managed.disableServiceAccountKeyCreation"]' \
     "organizations/${GCP_ORG_ID}/policies/iam.managed.disableServiceAccountKeyCreation"
   terragrunt import 'google_org_policy_policy.managed["compute.managed.restrictProtocolForwardingCreationForTypes"]' \
     "organizations/${GCP_ORG_ID}/policies/compute.managed.restrictProtocolForwardingCreationForTypes"
   terragrunt import 'google_org_policy_policy.boolean["iam.automaticIamGrantsForDefaultServiceAccounts"]' \
     "organizations/${GCP_ORG_ID}/policies/iam.automaticIamGrantsForDefaultServiceAccounts"
   terragrunt import 'google_org_policy_policy.boolean["iam.disableServiceAccountKeyUpload"]' \
     "organizations/${GCP_ORG_ID}/policies/iam.disableServiceAccountKeyUpload"
   ```

   Inventory first: a fresh organization might not contain every policy. Review each import
   and require a zero-change saved plan for the seven adopted baselines before adding the
   remaining Mindclade policies. `ORG_POLICY_ACTIVATION_PHASE=baseline` is deliberately
   cataloged for this first plan. Change it to `extended` only in a later reviewed governance
   change after every additional constraint passes Policy Simulator and lockout rehearsal.
7. Import other approved existing resources
   into the matching unit; never accept a plan that recreates or deletes them merely to make
   the import fast.
8. Open a pull request and review affected plans in dependency order. Unexpected project,
   network, KMS, stateful storage, or production-cluster replacement is a stop condition.

## Activate by scope

1. Qualify the plan identity as read-oriented and unable to apply.
2. Qualify each apply identity against only its declared scope and protected environment.
3. Merge the reviewed import.
4. Confirm the push selects only the minimum expected scopes and creates exact one-day plan
   bundles for the merged commit.
5. Approve the first scope in dependency order. Start with required foundation units, then
   development, staging, and production; do not use a repository-wide simultaneous apply as
   an import shortcut.
6. Follow [production activation gates](production-activation-gates.md) before the first
   production mutation and [GitOps handoff](gitops-handoff.md) before Argo activation.

## Verify

- account and module-interface validation pass;
- applied plan context and checksums match the merged commit;
- each unit owns one expected state prefix and no cross-environment dependency appears;
- negative authorization tests prove scope identities cannot cross boundaries;
- fresh plans are empty after each activated scope; and
- `gitops` receives cloud prerequisites without this repository installing Kubernetes state.

The platform import order is `.github`, `bootstrap`, `github-config`,
`infrastructure-live`, then `gitops`.
