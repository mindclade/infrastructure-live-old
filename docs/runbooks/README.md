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
| [Cloud SQL restore](cloud-sql-restore.md) | Restore a database into an isolated target and prove data/application integrity |
| [Failed production apply](failed-production-apply.md) | Contain and recover a partial or failed live apply |
| [GKE reconstruction](gke-reconstruction.md) | Recreate the cluster control plane and hand back to GitOps |
| [Nix binary-cache activation](nix-binary-cache-activation.md) | Qualify, activate, and safely detach the private Attic cache |
| [Organization-policy rollback](org-policy-rollback.md) | Remove a bad normal-plane policy change without weakening the estate broadly |
| [Protected-bucket restore](protected-bucket-restore.md) | Recover versioned data without overwriting the protected source bucket |
| [security.txt publication](security-txt-publication.md) | Publish, qualify, renew, and roll back RFC 9116 contact files |
| [State lock stuck](state-lock-stuck.md) | Verify ownership before force-unlocking state |
| [VPC Service Controls denial](vpc-sc-denial.md) | Diagnose dry-run or enforced perimeter denials |
| [Workload identity and holdout qualification](workload-identity-holdout-qualification.md) | Prove exact KSA/GSA trust and evaluation-data denial |

## Next runbooks

Before production activation, add and drill GPU capacity exhaustion, cluster upgrade, and cost
spike procedures. Drill the database, protected-bucket, organization-policy, and DNS delegation
rollback procedures in scratch or staging; use a non-mail domain before migrating
`mindclade.com`.

## Format

Each runbook must cover symptoms, impact, read-only diagnosis, resolution, recovery or rollback,
escalation, and prevention. Destructive or state-mutating commands must identify their approval
gate and exact target.

Runbooks do not grant authority. Production, destructive, state, and break-glass operations
still require their configured identities and approvals.
