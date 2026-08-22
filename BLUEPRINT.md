# Mindclade · `infrastructure-live` production blueprint

**Repository class:** `production-control`  
**Visibility:** `private`  
**Default branch:** `main`

## Authoritative responsibilities

- `normal-gcp-organization-infrastructure`
- `folders`
- `org-policy`
- `environments`
- `networks`
- `projects`
- `gke`
- `managed-cloud-services`

## Explicit exclusions

- `ring0-state-foundation`
- `argocd-installation`
- `kubernetes-desired-state`
- `application-source`

## Operating invariant

All changes are pull-request reviewed, subject to CODEOWNERS and required checks, merged through the configured queue for protected repositories, and performed by narrowly scoped identities. Live-system qualification evidence is separate from source completeness.

## External module-release gate

Reusable Terraform implementations remain owned by `mindclade-internal-monorepo`. Every PR plan
and exact merged-SHA plan must run `scripts/validate-module-interfaces.py` against the exact pinned
module refs before Terraform is allowed to plan. A missing module, scaffold-only module, or
undeclared live input is a hard failure; `infrastructure-live` never vendors around that failure.
