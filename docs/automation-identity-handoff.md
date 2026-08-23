# Automation identity handoff

The enterprise control plane uses a two-stage ownership model.

## Ring 0 (`bootstrap`)

Bootstrap creates:

- the GitHub Workload Identity Federation pool and repository-isolated providers;
- a dedicated `gh-bazel-cache` provider with one pull-request read route and separate protected
  main, merge-queue, and scheduled-nightly write routes;
- six capability-specific ARC provider conditions and exact protected-main/release principals;
- one read-only infrastructure plan service account;
- foundation, development, staging, and production apply service accounts;
- billing-user bindings required to attach projects;
- the empty private-module-reader secret container.

Bootstrap does not grant the environment identities broad organization authority.

Bootstrap contract `2.0.0` additionally creates `gh-workstation-image`, constrained to the exact
internal-monorepo caller on protected `main`, the `workstation-image-publication` environment,
immutable repository IDs, `workflow_dispatch`, and the exact `v5.0.0` reusable publication
workflow. Its subject prefix cannot impersonate any artifact-release or cache identity.

## Normal foundation (`infrastructure-live`)

`1-org/automation-iam` runs with the foundation apply identity after the top-level folders
exist. It grants each environment apply identity an inherited role set only on its matching
folder. The identities cannot mutate another environment through those bindings.

It creates distinct normal-plane canary, builder, qualification-reader, qualifier, signer, and
promoter service accounts. Each account is bound only to its bootstrap-exported capability
principal. The exact immutable-ID subject, trusted-main caller, push event, provider audience,
and governed workflow version must all agree: v5 for qualification reading and promotion, and v4
for every other artifact capability. Provider-specific subject prefixes prevent
one accepted ARC token from crossing into another capability's IAM binding. The IDs come from
bootstrap outputs and are never invented here.
See [`supply-chain-signer-contract.md`](supply-chain-signer-contract.md).

### Bazel cache identity handoff

The source contract for `1-org/automation-iam` creates separate `bazel-cache-reader` and
`bazel-cache-writer` service accounts in the common CI project. It binds only the exact
bootstrap-exported route principals: pull requests may impersonate the reader, while protected
main pushes, merge-group validation, and scheduled nightly runs may impersonate the writer.
Manual dispatch, tags, feature branches, alternate workflows, wrong immutable repository IDs,
and wrong provider audiences remain outside the provider contract.

The applied normal-plane outputs are the only authoritative handoff values:

```text
WIF_PROVIDER_BAZEL_CACHE
SA_BAZEL_CACHE_READER
SA_BAZEL_CACHE_WRITER
```

Do not construct these values from naming conventions. `github-config` may publish them only
after protected automation applies bootstrap contract `2.0.0` and the foundation IAM unit, then
connected qualification proves each positive route and the corresponding cross-route negative
cases. The cache bucket remains independently owned by
[`5-workloads/ci/bazel-remote-cache`](../5-workloads/ci/bazel-remote-cache/README.md); its module
owns bucket IAM and exports the authenticated endpoints. KMS owns the Cloud Storage service-agent
grant. This source change does not prove that any provider, account, binding, key grant, or bucket
exists.

The applied-output exporter retains these three values in handoff contract `1.5.0`, preserving
the production-eligibility and cache inventories from `1.3.0`/`1.4.0`. It requires the authoritative
`bazel_cache_identity_contract` Terraform output to match `BAZEL_CACHE_IDENTITY_JSON` byte-for-byte,
then independently verifies the exact provider, routes, immutable repository IDs, and distinct
common-CI reader/writer accounts. Missing applied state, a stale bootstrap JSON value, or any
substitution blocks export.

The foundation identity remains the only automation principal for:

- organization policy;
- folder hierarchy and cross-environment controls;
- centralized security and logging;
- authoritative DNS and shared networking;
- the environment-identity handoff itself.

### Workstation image publication handoff

`1-org/automation-iam` creates a dedicated normal-plane `workstation-image-pub` service account
and binds only the bootstrap-exported workstation-image principal. It receives no project role.
The create-only source bucket grants the account object creation and read-back solely so the
workflow can publish and verify a content-addressed raw-disk archive. The development Compute
service agent receives read access for Terraform image creation.

The authoritative normal-plane outputs are:

```text
WIF_PROVIDER_WORKSTATION_IMAGE
SA_WORKSTATION_IMAGE_BUILDER
```

`github-config` may publish these values only from applied output; it must not derive the service
account email from naming convention. The workflow also consumes `CI_PROJECT_ID` and
`WORKSTATION_IMAGE_BUCKET` from the applied source-bucket handoff. Publication retains the exact
object generation, source SHA-256, embedded contract SHA-256, and clean source commit. Those four
artifact values feed the protected infrastructure plan; Terraform alone creates the Compute
Image. No source contract claims any provider, account, bucket, object, or image is live.

### GitOps identity re-export

`5-workloads/shared/control-plane-identities` is authoritative for both GitOps workflow
identities and for the isolated production-qualification reader, writer, and evaluator. The
evaluator uses a keyless, short-lived service-account JWT through IAP; the staging and production
admin workload principals alone can invoke the HSM-backed Ed25519 decision signer. Its applied
outputs expose the exact non-secret handoff values as:

```text
SA_GITOPS_RENDER
SA_GITOPS_VERIFIER
WIF_PROVIDER_PRODUCTION_QUALIFICATION
SA_PRODUCTION_QUALIFICATION_READER
SA_PRODUCTION_QUALIFICATION_WRITER
SA_PRODUCTION_QUALIFICATION_EVALUATOR
PRODUCTION_QUALIFICATION_PROJECT
PRODUCTION_QUALIFICATION_PRIVATE_KEY_SECRET
PRODUCTION_QUALIFICATION_BUCKET
PRODUCTION_ELIGIBILITY_SIGNING_KEY_ID
PRODUCTION_ELIGIBILITY_KMS_KEY_VERSION
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

The destination must be outside the repository. The generated `1.5.0` file is mode 0600 and
carries all six ARC service accounts plus the exact GitOps, qualification, Bazel-cache,
workstation-image publisher/source-bucket, evidence-bucket, attestor, project, and immutable
key-version values. It compares the applied qualification, Bazel-cache, and workstation-image WIF
contracts byte-for-byte with their bootstrap JSON inputs before exporting.
Feed that file to
the `github-config` exporter, review its resulting plan, then reapply `github-config` so the
GitOps and monorepo repositories receive the authoritative values. Repeat the export and
reviewed governance apply after any identity, attestor, or key-version replacement. Until this
handoff has completed, GitOps render/provenance and production artifact signing are not
activation-ready.

`account.hcl` is a stable `get_env()` contract. The bootstrap exporter requires a clean checkout,
records its full source commit, hashes the complete applied `platform_contract`, and emits the
versioned `BOOTSTRAP_ACCOUNT_HANDOFF_JSON` record into the ignored `.account.env` file. Protected
automation must publish that exact non-secret JSON as a repository variable alongside the
individual state-bucket and service-account variables. Runtime validation rejects any duplicate
whose value differs from the applied-output record, including `TFSTATE_BUCKET_PRODUCTION` and
`SA_TF_LIVE_APPLY_PRODUCTION`; malformed records produce stable redacted error codes. Saved apply
artifacts contain the exact generated account contract, and apply fails if those inputs change
after planning. This source contract does not claim that the repository variable has been
published or that connected bootstrap output has been reviewed.

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
