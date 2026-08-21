<!-- mindclade-doc: runbook-index@1 -->

# Infrastructure Live runbooks

> **Platform Foundation · Incident recovery**  
> Symptom-first procedures for restoring the Google Cloud estate while preserving state,
> evidence, and protected apply boundaries.

## Available runbooks

| Runbook | Purpose |
| --- | --- |
| [Binary Authorization blocked deployment](binauthz-blocked-deploy.md) | Diagnose missing or invalid deployment evidence |
| [Cloud DNS delegation](dns-delegation.md) | Preflight, cut over, validate, and roll back registrar delegation |
| [Failed production apply](failed-production-apply.md) | Contain and recover a partial or failed live apply |
| [GKE reconstruction](gke-reconstruction.md) | Recreate the cluster control plane and hand back to GitOps |
| [State lock stuck](state-lock-stuck.md) | Verify ownership before force-unlocking state |
| [VPC Service Controls denial](vpc-sc-denial.md) | Diagnose dry-run or enforced perimeter denials |

## Next runbooks

Before production activation, add and drill GPU capacity exhaustion, cluster upgrade, cost
spike, Cloud SQL restore, protected-bucket restore, and organization-policy rollback
procedures. Drill the DNS delegation rollback on a non-mail domain before migrating
`mindclade.com`.

## Format

Each runbook must cover symptoms, impact, read-only diagnosis, resolution, recovery or rollback,
escalation, and prevention. Destructive or state-mutating commands must identify their approval
gate and exact target.

Runbooks do not grant authority. Production, destructive, state, and break-glass operations
still require their configured identities and approvals.
