<!-- mindclade-doc: runbook@1 -->

# Roll back an organization-policy regression

Owner: Cloud platform. Required actors: a primary operator and a distinct security observer. This
procedure covers normal-plane organization policies owned by `infrastructure-live`; Ring-0 policy
remains owned by `bootstrap`.

## Symptoms, impact, and containment

New denials across unrelated projects, failed service-agent creation, blocked cluster/database
operations, or policy dry-run deltas immediately after an apply indicate a possible regression.
Freeze applies in the affected environment and preserve the plan, apply log, audit log, constraint,
inheritance chain, and exact source SHA. Do not edit policy in Cloud Console.

Abort a drill if its target resolves above the declared scratch/staging folder, if the proposed
change disables a security baseline, or if the current effective policy cannot be captured.

## Diagnose without mutation

1. Identify the denied permission and constraint from audit logs.
2. Read the effective policy at organization, folder, and project scope and compare it with the
   reviewed Terraform plan and previous qualified commit.
3. Determine whether the failure is the policy value, inheritance, policy ordering, or a missing
   service-agent exception. Verify that the authoritative root is under the expected environment.
4. Produce a targeted rollback plan from a revert commit. The plan must affect only the named
   constraint and scope.

## Recover and verify

After protected environment approval, the authorized apply workflow may apply the reviewed revert.
Never use `gcloud org-policies set-policy` as a shortcut. Stop if plan/apply drift appears or the
target ID differs. Verify effective policy inheritance, repeat the previously denied read-only or
scratch operation, inspect audit logs, and run a clean Terraform plan.

Success requires the expected constraint to be restored, no unrelated policy delta, the affected
service healthy, and a clean follow-up plan. Record measured RPO/RTO, operators, source revisions,
commands, evidence hashes, failures, corrective actions, and next drill date in report v2.
