<!-- mindclade-doc: contributing@1 -->

# Contributing to Mindclade · `infrastructure-live`

Org-wide conventions are the canonical
[`CONTRIBUTING.md`](https://github.com/mindclade/.github/blob/main/CONTRIBUTING.md).
This file covers what is different here.

*(This exists because `.github` is internal, so nothing inherits. See `SECURITY.md`.)*

## Before you start

```sh
nix develop                                    # terraform 1.15.9, terragrunt 1.1.2, gcloud
python3 scripts/bootstrap-account.py ../bootstrap    # generate .account.env from bootstrap outputs
```

`account.hcl` is a stable `get_env()` contract. Source `.account.env` locally; every generated value comes from `terraform output` in the
bootstrap repo — do not fill them in by hand, because a wrong state bucket produces a second
parallel state that nothing reconciles.

Module fetches cross into the `Mindclade` org, so the Terraform App must be installed there
too. Locally your `gh auth` credential helper covers it.

## Activating an optional unit

The live development, staging, and production trees are populated. Optional physical
connectivity remains excluded until circuits, locations, and attachment identifiers have
been approved. Copy the shape of
[`5-workloads/development/gke`](5-workloads/development/gke/terragrunt.hcl) when adding a new
module-backed unit; do not copy an environment tree wholesale merely to create scale.

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

- A successful saved plan for every changed unit. Raw plan output is a one-day,
  access-controlled workflow artifact; it is never copied into a pull-request comment.
- For production paths: `@platform` and `@security`, two approvals, code-owner review.
- Review the destructive-change classification and the saved plan before approval.
- For any unresolved production activation gate, link the approved change or recovery record.

## Local checks

```sh
terragrunt hcl fmt --check --diff
terraform fmt -check -recursive
python3 scripts/validate-account.py
python3 scripts/validate-live-tree.py
python3 scripts/validate-dependency-order.py
python3 scripts/validate-production-contract.py
python3 scripts/plan-changed.py origin/main # only what your branch touches, plus dependents
pre-commit install
pre-commit run --all-files
```

## Never paste plan output containing state

Terraform state and plans can contain sensitive live-estate values even when Terraform marks
an output sensitive. Never paste raw state or plan output into an issue, pull request, or chat.


## Contributor authorization and intellectual property

A contribution may be submitted only by a person authorized under a current
written employment, contractor, assignment, or other contribution agreement
with Mindclade, LLC. Before opening or updating a pull request, the contributor
must confirm that:

- they have the right and authority to submit every part of the contribution;
- first-party work is covered by the contributor's controlling written
  agreement with Mindclade, LLC.;
- third-party code, data, models, media, fonts, specifications, and generated
  material are identified with their source, version, license, provenance, and
  required notices;
- the contribution contains no material whose confidentiality, license,
  consent, acceptable-use terms, export controls, or other restrictions
  prohibit submission; and
- the change description and validation evidence are complete and accurate.

By submitting or updating a pull request, the contributor represents that these
statements are true. Submission is not acceptance and does not by itself alter
ownership, grant a license, or replace the controlling written agreement.
Signed commits establish source identity and integrity; they are not a
substitute for the required written agreement.

If authorization or ownership is unclear, stop before submission and use the
legal or contract channel named in the applicable agreement. Do not place
confidential material in a public issue or an unapproved email.
