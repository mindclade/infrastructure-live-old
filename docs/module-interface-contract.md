<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

<!-- mindclade-doc: reference@1 -->

# Terraform module interface contract

> **Audience:** module authors and reviewers changing live Terragrunt inputs.
> **Outcome:** keep live configuration compatible with an immutable, published module interface.

`infrastructure-live` owns live Google Cloud desired state. Reusable Terraform module
implementation remains in `mindclade/mindclade-internal-monorepo`, as required by the enterprise
platform authority boundary.

## Contract

Every live unit pins its module to a protected full semantic release tag or a commit SHA. Before a
PR plan or an exact merged-SHA plan can run, CI checks out the monorepo as **data** and runs
`scripts/validate-module-interfaces.py`. The preflight verifies that each exact pinned ref contains
the requested module, every Terragrunt input key is declared by that module, and every module
variable without a default is supplied by the unit or its `_envcommon` contract. It executes no
monorepo code.

The companion `scripts/validate-capacity-contract.py` gate verifies that the accelerator profiles
selected by every live environment are exactly the profiles exposed by the same monorepo ref's
Kubernetes GPU contract and Kueue `ResourceFlavor` objects. It also requires matching capacity
namespaces, held queues, qualification jobs, and training overlays. This prevents a valid Terraform
GPU pool and a valid Kubernetes tree from silently disagreeing on H100, H200, or B200 scheduling.

The `scripts/validate-workload-identity-contract.py` gate applies the same immutable-ref rule to
GKE identity. It requires every environment's typed KSA-to-GSA binding, the exact environment
overlay annotation, the three holdout deny principals, and the evaluator's additive bucket-level
object-viewer member to describe the same identities. Candidate mode
checks the planned worktree only and cannot substitute for the protected module/Kubernetes tag.

A missing module, a scaffold with no variables, an undeclared live input, or an omitted required
input is a hard failure. The plan then performs Terraform's authoritative type, value, graph, and
provider validation. This prevents `infrastructure-live` from silently getting ahead of the module
release it consumes without moving reusable module ownership into this repository.

During a coordinated cross-repository release, callers may point at the monorepo's one explicit
`status = "planned"` contract version before its protected tag exists. The source-review gate reads
only callers at that exact candidate version from the local monorepo worktree; all older tags and
SHAs are still read from their immutable Git trees. This proves source compatibility, not release
provenance. The exact-ref gate remains fail-closed until the release operator publishes the tag.

| Change | Required first action |
|---|---|
| Add or rename a module input | Release the compatible module interface, then update its live pin |
| Remove a module input | Remove all live consumers before or with the compatible pin update |
| Change an input type or meaning | Treat as a breaking interface change and document migration |
| Add a live component | Pin an exact module ref and declare only published variables |

The organization Binary Authorization KMS unit is the one explicit ring-only composition.
It sets `ring_only = true` with empty `keys` and `signing_keys`; the dependent Binary
Authorization states remain the sole owners of attestor CryptoKeys in that protected ring.
The module rejects both an empty ordinary KMS owner and any key declared by the ring-only
owner, preventing a second CryptoKey state owner.

## Validate before review

Run the interface preflight directly when diagnosing a mismatch:

```sh
make validate-module-interfaces MONOREPO=../mindclade-internal-monorepo
make validate-capacity-contract MONOREPO=../mindclade-internal-monorepo
make validate-workload-identity-contract MONOREPO=../mindclade-internal-monorepo
```

For the planned v0.4.0 source review, run the separate candidate gate:

```sh
make validate-module-candidate MONOREPO=../mindclade-internal-monorepo CANDIDATE_MODULE_VERSION=v0.4.0
make validate-capacity-candidate MONOREPO=../mindclade-internal-monorepo CANDIDATE_MODULE_VERSION=v0.4.0
make validate-workload-identity-candidate MONOREPO=../mindclade-internal-monorepo CANDIDATE_MODULE_VERSION=v0.4.0
nix develop .#ci --command make validate-source-integration MONOREPO=../mindclade-internal-monorepo
```

A candidate pass must never be presented as an immutable-ref pass and must not authorize a plan or
apply. After the protected tag is published from the reviewed commit, remove reliance on candidate
mode by running the exact integration target:

```sh
nix develop .#ci --command make validate-integration MONOREPO=../mindclade-internal-monorepo
```

The preflight is structural; a successful Terraform plan is still the authoritative semantic and
provider-level check. Never bypass the preflight with an unpinned ref or by duplicating a reusable
module in this repository.
