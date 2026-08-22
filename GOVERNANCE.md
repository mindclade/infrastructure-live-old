<!-- mindclade-doc: governance@1 -->

# Mindclade governance · `infrastructure-live`

| Document control | Value |
| --- | --- |
| Owner | Mindclade Platform |
| Version | 1.0 |
| Last reviewed | August 21, 2026 |
| Authority | Live non-Ring-0 GCP organization and environment infrastructure |

## Authority boundary

The Terragrunt live tree is authoritative only for the scopes listed in
[contracts/repository.yaml](contracts/repository.yaml). Ring-0 state and
federation belong to `bootstrap`; Argo CD and Kubernetes desired state belong
to `gitops`; application source belongs to the monorepo.

## Decisions and approvals

Development and staging changes require passing checks, one approval, and
code-owner review. Production, IAM, organization-policy, network, KMS, backup,
DNS, GKE, or workflow-authorization changes require Platform and Security
review and two qualified approvals. Applies run only through the protected
environment against an integrity-checked plan for the reviewed commit.

## Evidence and application

A pull request records every affected unit, dependency order, replacements and
destroys, cost and availability impact, migration, rollback, and exact
validation commands. Raw state and saved plans remain access-controlled
artifacts and are never pasted into review text.

## Exceptions and review

Emergency change follows the incident process, uses the narrowest time-bounded
authorization, and creates a reviewed reconciliation change immediately.
Emergency access does not waive security, confidentiality, licensing, audit,
or evidence requirements.

Drift is checked automatically. Production access, destructive-change policy,
backup and recovery, DNS ownership, and exception records are reviewed at
least quarterly. Organization-wide defaults are defined in
[`mindclade/.github/GOVERNANCE.md`](https://github.com/mindclade/.github/blob/main/GOVERNANCE.md).
