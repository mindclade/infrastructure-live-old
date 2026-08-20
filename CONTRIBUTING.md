# Contributing to `infrastructure-live`

Org-wide conventions are the canonical
[`CONTRIBUTING.md`](https://github.com/Mindclade/.github/blob/main/CONTRIBUTING.md).
This file covers what is different here.

*(This exists because `.github` is internal, so nothing inherits. See `SECURITY.md`.)*

## Before you start

```sh
nix develop                                    # terraform 1.15.9, terragrunt 1.1.2, gcloud
./scripts/bootstrap-account.sh ../bootstrap    # generate .account.env from bootstrap outputs
```

`account.hcl` is a stable `get_env()` contract. Source `.account.env` locally; every generated value comes from `terraform output` in the
bootstrap repo — do not fill them in by hand, because a wrong state bucket produces a second
parallel state that nothing reconciles.

Module fetches cross into the `Mindclade` org, so the Terraform App must be installed there
too. Locally your `gh auth` credential helper covers it.

## Filling in a stub unit

Most units are scaffolding with an `exclude` block. Copy the shape of
[`5-workloads/development/gke`](5-workloads/development/gke/terragrunt.hcl) — it is the worked
reference — then delete the `exclude` block.

Four things every real unit needs: `include "root"`, `include "envcommon"`, typed `dependency`
blocks with mock outputs, and only the inputs that genuinely differ from the envcommon default.

## A missing `dependency` block is a race, not a missing input

Terragrunt builds its apply order from `dependency` blocks. Omit one and it will apply two
units in parallel that should have been sequential — and the failure looks like a transient
API error, not an ordering bug.

If a unit reads another unit's output, it needs a `dependency` block. If it merely needs
another unit applied first, it still needs one.

## `mock_outputs_allowed_terraform_commands` is the important half

```hcl
mock_outputs_allowed_terraform_commands = ["plan", "validate", "init"]
```

Without it, mocks are used during `apply` too, and the resource gets built against a fake id.
The apply succeeds. The resource is simply wrong.

## Modules are pinned to a semver tag, never a branch

That rule is the entire reason this repository is separate from the modules. A branch means a
merge to the monorepo's `main` changes what the next production apply builds, with no diff
here and nothing to review.

Bumping a module is a one-line PR that says exactly which version moved.

## What a PR needs

- Plan output for every changed unit — `plan.yml` comments it automatically.
- For production paths: `@platform` and `@security`, two approvals, code-owner review.
- Grep your own plan for `will be destroyed` and `must be replaced`.

## Local checks

```sh
terragrunt hcl fmt --check --diff
./scripts/plan-changed.sh origin/main       # only what your branch touches, plus dependents
pre-commit install
pre-commit run --all-files mindclade-license-header
```

## Never paste plan output containing state

Terraform state for this repository holds every value marked sensitive across the live estate
in plaintext. Sanitise before pasting into an issue, a PR, or chat.
