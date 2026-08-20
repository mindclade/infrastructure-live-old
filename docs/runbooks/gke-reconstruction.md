<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

<!-- mindclade-doc: runbook@1 -->

# Reconstruct a lost GKE cluster

> **Use when:** a GKE cluster is deleted, irrecoverable, or unsafe to operate.
> **Impact:** the affected trust domain is unavailable while cloud authorities and data remain.
> **Primary owner:** incident commander with infrastructure, GitOps, service, and data recovery owners.
> **Escalate:** before destructive replacement, recovery-point selection, or reopening traffic.

## Symptoms

The cluster is irrecoverable, deleted, or unsafe to continue operating.

## Impact

In-cluster services and workloads are unavailable in the affected trust domain. Cloud data,
artifact, network, IAM, and Git authorities must remain intact.

## Diagnosis

1. Declare an incident and preserve GKE, Cloud Audit Logs, Terraform, GitOps, Binary
   Authorization, and KMS evidence.
2. Confirm the authoritative infrastructure and GitOps commits, artifact digests, backup
   recovery points, and affected data services.
3. Verify state integrity and determine whether reconstruction can retain the current
   network, service identities, databases, buckets, and KMS keys.

## Resolution

1. Recover bootstrap state/WIF and the `infrastructure-live` state path before any cluster
   work. Never depend on the failed cluster for recovery credentials.
2. Obtain a reviewed exact saved plan for the affected GKE and node-pool units. Destruction
   or replacement of a production cluster is a critical change.
3. Recreate cloud-side cluster prerequisites through the protected apply workflow.
4. Install the pinned Argo CD profile and root application using the
   [GitOps handoff](../gitops-handoff.md). Terraform does not install Argo CD.
5. Allow GitOps to reconcile policies, operators, namespaces, and digest-pinned workloads.
6. Restore stateful data only from a verified recovery point; validate schema, integrity,
   holdout isolation, and serving behavior before reopening traffic.

## Prevention

Exercise this sequence in a clean staging trust domain and record recovery time, data loss,
manual dependencies, and corrective work.

## Verify recovery

- A no-change infrastructure plan confirms the reconstructed cloud state.
- Argo CD and every intended Application are healthy at the recorded GitOps commit.
- Binary Authorization and admission-policy negative tests still reject unqualified changes.
- Restored data passes integrity, consistency, and service-level acceptance checks.
- Monitoring, alerting, backup, and audit export paths work independently of the recovered cluster.

Reopen traffic only after the incident commander records recovery-point acceptance, residual data
loss, service validation, security-control evidence, and rollback or forward-recovery ownership.

## Escalation and handoff

At each recovery boundary, provide authoritative infrastructure/GitOps commits, cluster identity,
state generations, recovery point, plans and mutations, admission evidence, service checks, data
loss estimate, and current owner. Escalate destructive replacement and traffic reopening to the
incident commander and security/data owners.
