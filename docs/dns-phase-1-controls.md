<!--
Copyright © 2026 Mindclade, LLC. All Rights Reserved.
Mindclade Proprietary and Confidential.
SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
-->

# DNS Phase 1 Controls

Phase 1 is source-only. It introduces fail-closed governance and deterministic
change artifacts without applying Terraform, changing DNS delegation, publishing
a release, or mutating IAM.

## Immutable evidence

The file `contracts/dns-change-evidence.json` is the repository projection of
restricted evidence. Evidence content does not belong in Git. The contract stores
only an immutable `gs://` object URI, observation time, SHA-256, reviewer, review
time, and optional expiry.

The configured bucket must have object versioning and a locked retention policy.
A gate cannot become `pending_review` until its URI includes a GCS generation.
A gate cannot become `approved` without an independent reviewer and review time.
The recovered Cloudflare export and Workspace audit remain `pending_upload`; the
repository does not claim they have been uploaded or reviewed.

## Derived readiness

Run:

~~~bash
python3 scripts/validate_dns_governance.py
~~~

The `inventory_complete` and `delegation_ready` values must equal the state
derived from portfolio gates, per-domain gates, evidence expiry, and
public-address exception approvals. Editing either boolean without satisfying
its evidence gates fails validation.

## Public-address exceptions

The file `contracts/dns-public-record-exceptions.json` adds justification, change
record, approver, approval time, and optional expiry to each allowlisted A, AAAA,
or CNAME key. Its keys must exactly match each domain's canonical
`public_record_allowlist`. Only the reviewed Squarespace records for
`mindclade.ai` and `mindclade.dev` are eligible. They remain pending review.

## Exact-commit module validation

Validate the infrastructure interface against an exact local monorepo commit
before the immutable release exists:

~~~bash
make validate-release-candidate \
  MONOREPO=../mindclade-internal-monorepo \
  CANDIDATE_MODULE_VERSION=v0.4.0 \
  CANDIDATE_MODULE_REF=<40-character-lowercase-commit-sha>
~~~

The wrapper validates a detached local clone. It neither reads uncommitted
candidate files nor substitutes the commit requirement with a branch or short
SHA. Protected merge and production callers must still use the published,
immutable release tag.

## Cutover packets

The script `scripts/generate_dns_cutover_packets.py` consumes separately captured
incumbent and target snapshots. All timestamps and the `CHG-` identifier are
explicit, so the output is deterministic. The generator embeds full before/after
records, snapshot hashes, evidence-manifest hash, readiness blockers, read-only
preflight commands, and DNSSEC-safe rollback steps.

The output directory is write-once, mode `0700`, with packet files mode `0600`
and a `SHA256SUMS` manifest. Use `--require-ready` for an approved packet. Without
it, incomplete domains produce an explicit `DRAFT`; they never become silently
actionable.
