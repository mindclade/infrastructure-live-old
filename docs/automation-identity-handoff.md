# Automation identity handoff

The enterprise control plane uses a two-stage ownership model.

## Ring 0 (`bootstrap`)

Bootstrap creates:

- the GitHub Workload Identity Federation pool and repository-isolated providers;
- six capability-specific ARC provider conditions and exact protected-main/release principals;
- one read-only infrastructure plan service account;
- foundation, development, staging, and production apply service accounts;
- billing-user bindings required to attach projects;
- the empty private-module-reader secret container.

Bootstrap does not grant the environment identities broad organization authority.

## Normal foundation (`infrastructure-live`)

`1-org/automation-iam` runs with the foundation apply identity after the top-level folders
exist. It grants each environment apply identity an inherited role set only on its matching
folder. The identities cannot mutate another environment through those bindings.

It creates distinct normal-plane canary, builder, qualification-reader, qualifier, signer, and
promoter service accounts. Each account is bound only to its bootstrap-exported capability
principal. The exact immutable-ID subject, trusted-main caller, push event, provider audience,
and immutable v4 reusable workflow must all agree. Provider-specific subject prefixes prevent
one accepted ARC token from crossing into another capability's IAM binding. The IDs come from
bootstrap outputs and are never invented here.
See [`supply-chain-signer-contract.md`](supply-chain-signer-contract.md).

The foundation identity remains the only automation principal for:

- organization policy;
- folder hierarchy and cross-environment controls;
- centralized security and logging;
- authoritative DNS and shared networking;
- the environment-identity handoff itself.

### GitOps identity re-export

`5-workloads/shared/control-plane-identities` is authoritative for both GitOps workflow
identities and for the isolated production-qualification reader/writer pair. Its applied
outputs expose the exact non-secret handoff values as:

```text
SA_GITOPS_RENDER
SA_GITOPS_VERIFIER
WIF_PROVIDER_PRODUCTION_QUALIFICATION
SA_PRODUCTION_QUALIFICATION_READER
SA_PRODUCTION_QUALIFICATION_WRITER
PRODUCTION_QUALIFICATION_PROJECT
PRODUCTION_QUALIFICATION_PRIVATE_KEY_SECRET
PRODUCTION_QUALIFICATION_BUCKET
```

These values are outputs, not naming conventions. `github-config` must not construct or
hardcode either email. Initial activation is deliberately staged: apply this live unit and the
production Binary Authorization unit, then run the applied-output exporter from the exact clean
merged commit:

```bash
python3 scripts/export-applied-control-plane-handoff.py \
  --expected-source-commit "$MERGED_INFRASTRUCTURE_SHA" \
  --output /protected/evidence/infrastructure-control-plane-handoff.json
```

The destination must be outside the repository. The generated file is mode 0600 and carries
all six ARC service accounts plus the exact GitOps, qualification, evidence-bucket, attestor,
project, and immutable key-version values. It compares the applied qualification WIF contract
byte-for-byte with `PRODUCTION_QUALIFICATION_IDENTITY_JSON` from bootstrap before exporting.
Feed that file to
the `github-config` exporter, review its resulting plan, then reapply `github-config` so the
GitOps and monorepo repositories receive the authoritative values. Repeat the export and
reviewed governance apply after any identity, attestor, or key-version replacement. Until this
handoff has completed, GitOps render/provenance and production artifact signing are not
activation-ready.

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
