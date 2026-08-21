<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

<!-- mindclade-doc: runbook@1 -->

# Qualify GKE workload identity and holdout isolation

> **Use when:** activating or changing preprocessing/training Workload Identity Federation or
> the held-out evaluation bucket.
> **Impact:** an incorrect binding can expose research data or silently invalidate evaluation.
> **Primary owner:** platform security with research-data and GitOps owners.
> **Escalate:** before granting holdout access, removing a deny principal, or changing a KSA/GSA
> mapping.

## Preconditions

1. Record the reviewed `infrastructure-live`, monorepo, and GitOps commits. The monorepo module
   and Kubernetes source must be available at the protected `v0.4.0` tag, and the exact
   `make validate-integration` gate must pass. Candidate-mode evidence is insufficient.
2. Retain credentialed, non-destructive saved plans for the environment's
   `workload-identities` and `storage/gcs-holdout` units. Confirm that every GSA has zero
   project-wide roles and that the plan contains no service-account key resource.
3. Use staging first. Keep capacity quotas, queues, and deployment selections blocked while
   testing identity; this procedure does not authorize workload activation.
4. Use a digest-pinned qualification image admitted by Binary Authorization. Do not mint,
   export, log, or store a service-account key or access token.

## Read-only contract verification

For the selected environment, capture the applied Terraform outputs from the protected operator
context:

```sh
terragrunt output -json service_accounts
terragrunt output -json gke_ksa_members
```

Run those commands from exactly
`5-workloads/<environment>/workload-identities`. Verify all of the following:

- `preprocessing`, `training_h100`, `training_b200`, and `holdout_evaluator` are the
  only returned GSAs;
- the members select the environment platform project's GKE workload pool;
- the namespace/KSA pairs are respectively `mindclade-batch-cpu/mindclade-batch-cpu`,
  `mindclade-training-h100/mindclade-training-h100`, and
  `mindclade-training-b200/mindclade-training-b200`; the evaluator pair is
  `mindclade-evaluation/mindclade-holdout-evaluator`;
- each live KSA annotation equals its selected GSA email;
- each GSA IAM policy grants `roles/iam.workloadIdentityUser` only to its selected KSA member.

Capture the applied holdout deny policy and confirm that its principal set equals the same three
GSA emails, its exception set is empty, and its resource condition selects only the environment's
holdout bucket. Confirm separately that only `holdout_evaluator` receives the bucket-level
`roles/storage.objectViewer` member. Treat any missing, additional, inferred, project-wide, or
authoritative IAM grant as a hard failure.

## Connected negative tests

Use separately reviewed, suspended-by-default qualification Jobs through GitOps. Execute one Job
as each of the three KSAs and retain pod identity, image digest, Binary Authorization result,
command exit status, and Cloud Audit Log entry.

1. Prove the pod receives the intended GSA identity and cannot impersonate either sibling GSA.
2. Attempt object `get`, `list`, and `getIamPolicy` against the holdout bucket. Every operation
   must fail because of the named IAM deny rule, even if a temporary staging-only allow grant is
   introduced solely to prove deny precedence.
3. Confirm the same pod cannot read a different environment's research resources.
4. Remove any temporary allow through the protected saved-plan workflow and retain the
   zero-change follow-up plan.

Do not weaken the deny or add an exception to make a test pass. An unexpected success is a data
integrity incident: suspend evaluation publication, preserve audit evidence, and rotate any
affected holdout dataset under the research-data incident process.

## Evaluation-only positive test

Use only `mindclade-evaluation/mindclade-holdout-evaluator`. Prove it can read the qualified,
synthetic holdout object and cannot list unrelated objects, read another environment's bucket,
or impersonate any training identity. Re-run all training negative tests in the same change.
Project-wide viewer or Storage roles do not satisfy this gate.

## Rollback

Rollback is Git-mediated. First return the affected workload to a blocked selection and remove
its GSA annotation through the monorepo/GitOps release path. Then use a reviewed infrastructure
plan to revoke the narrow `roles/iam.workloadIdentityUser` member. Keep the holdout deny policy in
place throughout rollback. Never delete the protected service account, project, bucket, or deny
policy as an identity rollback shortcut.

## Evidence record

Retain source SHAs and protected tags, saved-plan and rendered-manifest digests, applied output
digests, exact KSA/GSA pairs, negative and positive test results, relevant audit-log references,
reviewers, operator, date, and requalification deadline outside Git. Raw tokens, credentials,
state, plans, and holdout data do not belong in the repository.
