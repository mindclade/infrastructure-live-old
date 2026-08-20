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
the requested module and that every Terragrunt input key is declared by that module. It executes no
monorepo code.

A missing module, a scaffold with no variables, or a live input that is not part of the module's
published interface is a hard failure. The plan then performs Terraform's authoritative semantic
validation. This prevents `infrastructure-live` from silently getting ahead of the module release
it consumes without moving reusable module ownership into this repository.

| Change | Required first action |
|---|---|
| Add or rename a module input | Release the compatible module interface, then update its live pin |
| Remove a module input | Remove all live consumers before or with the compatible pin update |
| Change an input type or meaning | Treat as a breaking interface change and document migration |
| Add a live component | Pin an exact module ref and declare only published variables |

## Validate before review

Run the interface preflight directly when diagnosing a mismatch:

```sh
make validate-module-interfaces MONOREPO=../mindclade-internal-monorepo
```

Then run the complete repository contract:

```sh
nix develop .#ci --command make validate-integration MONOREPO=../mindclade-internal-monorepo
```

The preflight is structural; a successful Terraform plan is still the authoritative semantic and
provider-level check. Never bypass the preflight with an unpinned ref or by duplicating a reusable
module in this repository.
