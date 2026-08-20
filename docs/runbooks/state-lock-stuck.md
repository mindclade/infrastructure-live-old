<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

# Terraform state lock appears stuck

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

## Prevention

Retain apply concurrency groups, bounded provider timeouts, GCS audit logs, and periodic
state-lock recovery drills.
