<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

<!-- mindclade-doc: runbook@1 -->

# Terraform state lock appears stuck

> **Use when:** a state unit remains locked after its apparent plan or apply has ended.
> **Impact:** changes to that unit are blocked; running infrastructure should be unaffected.
> **Primary owner:** state-unit owner with a second qualified operator.
> **Escalate:** when lock ownership is uncertain, an apply may still run, or state drift is detected.

## Symptoms

A plan or apply reports that the GCS state is locked after the workflow that acquired it has
ended.

## Impact

Changes to that one state unit are blocked. The existing infrastructure should continue to
run; urgency does not justify deleting lock or state objects.

## Diagnosis

1. Record the state prefix, lock identifier, operation, actor, source SHA, and creation time
   from the error.
2. Confirm no apply for that unit is running, queued, retrying, or awaiting environment
   approval. Check GitHub Actions and the state audit logs.
3. Contact the recorded lock owner when possible. A slow provider operation can outlive the
   visible step that initiated it.
4. Verify state generations/versions are intact. Do not download or paste state content.

## Resolution

1. Prefer allowing the owning operation to finish or cancel cleanly.
2. If two qualified operators prove the lock is orphaned, open a critical change record with
   the exact unit and lock ID.
3. Use Terraform's lock-release mechanism only against that exact ID and only from the
   controlled recovery environment. Never delete GCS state or lock objects directly.
4. Immediately run a read-only refresh/plan for that unit and investigate any drift before
   another apply.

## Verify recovery

- Audit and workflow evidence proves no prior operation remains active.
- The exact orphaned lock is gone and state generations remain intact.
- A locked read-only plan completes for the same unit.
- Any proposed drift is explained and reviewed before another apply.

Record the unit, lock ID, original actor/source SHA, reviewers, release action, validation result,
and audit timestamps. Stop and escalate rather than retrying force-unlock against a different ID.

## Escalation and handoff

Hand off the incident ID, unit/prefix, lock ID, owning operation and source SHA, workflow status,
audit timestamps, state generations, reviewers, release action, and fresh-plan result. Escalate when
any evidence suggests the operation is still active or state integrity is uncertain.

## Prevention

Retain apply concurrency groups, bounded provider timeouts, GCS audit logs, and periodic
state-lock recovery drills.
