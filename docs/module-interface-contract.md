<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

# Terraform module interface contract

`infrastructure-live` owns live Google Cloud desired state; reusable Terraform module
implementation remains in `mindclade/mindclade-internal-monorepo`, as required by the enterprise
platform authority boundary.

Every live unit pins its module to a protected full semantic release tag or a commit SHA. Before a
PR plan or an exact merged-SHA plan can run, CI checks out the monorepo as **data** and runs
`scripts/validate-module-interfaces.py`. The preflight verifies that each exact pinned ref contains
the requested module and that every Terragrunt input key is declared by that module. It executes no
monorepo code.

A missing module, a scaffold with no variables, or a live input that is not part of the module's
published interface is a hard failure. The plan then performs Terraform's authoritative semantic
validation. This prevents `infrastructure-live` from silently getting ahead of the module release
it consumes without moving reusable module ownership into this repository.
