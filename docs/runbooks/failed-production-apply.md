<!-- mindclade-doc: runbook@1 -->

# A protected production apply failed

> **Use when:** a protected foundation, partner, or production plan/apply workflow fails.
> **Impact:** one or more state units may be partially changed while other units remain isolated.
> **Primary owner:** incident commander and qualified infrastructure operator.
> **Escalate:** when mutation, lock ownership, account context, target unit, or plan provenance is
> unclear.

## Symptoms

- the `apply` workflow's `plan-exact-main` or `apply` job failed for the `production`,
  `foundation`, or `partners` scope;
- the workflow-created `infrastructure apply pipeline failed` incident issue is open; or
- Terragrunt reports a provider, lock, checksum, account-context, or partial-apply error.

## Impact and stop conditions

The affected scope or unit may be partially changed, while other state units remain
independent. Workflow concurrency prevents a second apply workflow from running in parallel.
Do not edit state, force-unlock, import, delete, or run a workstation apply until logs prove
the failure mode and no other operation owns the lock.

Stop and escalate if the plan bundle, commit, account context, target unit, or provider
mutation status cannot be established from preserved evidence.

## Diagnose

1. Link the workflow-created incident issue to the active incident and record the run URL,
   commit SHA, selected scope, optional unit, protected environment, and failure time.
2. Inspect the failed job without exposing secrets or downloading raw state:

   ```sh
   gh run view <run-id> --repo mindclade/infrastructure-live
   gh run view <run-id> --repo mindclade/infrastructure-live --log-failed
   ```

3. Determine the phase:

   | Phase | Mutation possible? | Next action |
   | --- | --- | --- |
   | Scope selection or account validation | No | Correct configuration in a pull request |
   | Exact plan creation or upload | No apply mutation | Correct the cause and replan |
   | Checksum, context, or destructive authorization | No apply mutation | Preserve the rejected artifact and replan |
   | Terragrunt apply | Yes | Read provider logs and run a fresh read-only plan |

4. Identify every unit that started applying. Do not assume the whole scope changed.
5. If an apply started, use a qualified read-only identity to create a fresh plan for only
   the affected unit. A non-empty plan describes the current delta; it does not by itself
   prove state corruption.

## Recover

Prefer a reviewed forward fix. Commit the smallest correction, merge it through normal
checks, and let the protected workflow generate a new exact plan for the merged SHA.

When the desired state is already correct and the failed operation only needs a safe retry,
dispatch the workflow against `main` for the explicit unit:

```sh
gh workflow run apply.yml \
  --repo mindclade/infrastructure-live \
  --ref main \
  -f scope=production \
  -f unit=5-workloads/production/<explicit-unit> \
  -f allow_destroy=false \
  -f change_reference=INC-<identifier>
```

Review the new classification and saved plan at the protected environment. If it contains a
delete or replacement, stop. Use `allow_destroy=true` only after an authorized reviewer has
confirmed the exact resources and the `change_reference` matches the approved incident,
change, security, or recovery record.

Restore state only when evidence proves state corruption and the state-recovery procedure
identifies the exact recoverable object. A partial provider apply normally requires refresh
and forward reconciliation, not state rollback.

## Verify recovery

- the successful apply commit matches current `main`;
- the plan bundle checksum, account context, scope, and unit checks all passed;
- a fresh plan for the affected unit is empty or contains only separately approved follow-up;
- dependent services and policy controls report healthy; and
- no state lock or unreviewed console change remains.

## Escalation and handoff

Provide the incident ID, workflow URL, source SHA, scope/unit, account context, failure phase, plan
bundle/checksum, provider logs, lock status, state generations, mutations, fresh plan, and remaining
risk. Escalate state corruption, unexplained mutation, or a destructive recovery decision before
another protected apply.

## Prevention

Attach the failure phase, provider error, affected units, recovery plan, and verification to
the incident. Create corrective work for missing preconditions, timeouts, provider behavior,
or insufficient validation, and close the workflow-created issue only after that work is
owned.
