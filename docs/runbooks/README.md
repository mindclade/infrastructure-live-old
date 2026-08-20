# Runbooks

Operational procedures for the live estate. Linked from `.github-private/profile/README.md`,
which is where someone on call will look first.

A runbook is written for someone who is tired, under pressure, and did not build the thing.
That means: exact commands, expected output, and what to do when the output differs.

## What exists

| Runbook | For |
|---|---|
| _(none yet)_ | |

## What to write first

Ordered by how likely you are to need it before you have written it:

1. **`gke-node-pool-exhaustion.md`** — GPU capacity unavailable in a region. Which regions to
   fail over to, how to move a Kueue queue, what to tell the affected team.
2. **`vpc-sc-denial.md`** — A request blocked by the perimeter. How to read the denial in the
   audit log, and how to distinguish a missing ingress rule from a genuine attack.
3. **`binauthz-blocked-deploy.md`** — An image rejected at admission. Which attestor is
   missing, how to verify the attestation exists, and the emergency exemption path.
4. **`state-lock-stuck.md`** — Cleared after a cancelled apply, and how to be sure no other
   apply is in flight before force-unlocking.
5. **`cluster-upgrade.md`** — Control plane and node pool upgrades, including the checkpoint
   sequence for in-flight training jobs.
6. **`cost-spike.md`** — Budget alert fired. How to find what is running, and how to stop it
   without taking production with it.

## Format

Keep each one to this shape:

```markdown
# <What is broken>

## Symptoms
What you saw that brought you here. Include the exact error text — that is what people
paste into search.

## Impact
Who is affected, and how urgently this needs fixing.

## Diagnosis
Commands, with expected output. Say what each result means.

## Resolution
Numbered steps. Exact commands. Note which are irreversible.

## Prevention
What change would stop this recurring. Link the issue if one exists.
```

The **Prevention** section is the one that earns the runbook its place. A runbook used three
times without that section being acted on is three incidents that were treated as weather.
