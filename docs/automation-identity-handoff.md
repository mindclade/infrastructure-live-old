# Automation identity handoff

The enterprise control plane uses a two-stage ownership model.

## Ring 0 (`bootstrap`)

Bootstrap creates:

- the GitHub Workload Identity Federation pool and repository-isolated providers;
- one read-only infrastructure plan service account;
- foundation, development, staging, and production apply service accounts;
- billing-user bindings required to attach projects;
- the empty private-module-reader secret container.

Bootstrap does not grant the environment identities broad organization authority.

## Normal foundation (`infrastructure-live`)

`1-org/automation-iam` runs with the foundation apply identity after the top-level folders
exist. It grants each environment apply identity an inherited role set only on its matching
folder. The identities cannot mutate another environment through those bindings.

The foundation identity remains the only automation principal for:

- organization policy;
- folder hierarchy and cross-environment controls;
- centralized security and logging;
- authoritative DNS and shared networking;
- the environment-identity handoff itself.

`account.hcl` is a stable `get_env()` contract. In CI, `github-config` exports verified
bootstrap outputs as repository variables; local operators generate the ignored `.account.env` file
before any plan or apply. Saved apply artifacts contain the exact generated account contract;
apply fails if those inputs change after planning.

## Live-only implementation exception

`1-org/automation-iam` and `5-workloads/shared/control-plane-identities` contain narrow local
Terraform roots. They bind repository/state owners and external identities, so they are not
reusable workload modules. All ordinary organization, network, project, storage, database,
cluster, and accelerator implementations continue to use immutable module releases from
`mindclade-internal-monorepo`.

## VPC Service Controls authority

VPC Service Controls is an organization-level security control even though each perimeter
protects one environment. The three `5-workloads/<environment>/vpc-sc-perimeter` units are
therefore selected and applied by the **foundation** identity. Environment apply identities
are explicitly excluded from those units. The foundation identity has state write access to
the three environment state buckets only for this cross-cutting control.
