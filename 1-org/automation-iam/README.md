<!-- mindclade-doc: reference@1 -->

# Environment automation IAM

> **Purpose:** hand bootstrap-created identities into the normal infrastructure authority model
> without granting cross-environment apply access.

Bootstrap creates the keyless identities but does not own normal environment hierarchy or
infrastructure policy. This foundation unit performs the one-way handoff by granting each
apply identity permissions inherited only within its own top-level environment folder.

The foundation identity remains the sole automation authority for organization policy,
centralized security/logging, shared DNS/networking, and cross-environment controls. Plan
uses a separate read-only identity. No human credential or service-account key is created.

## Contract

| Identity | Scope | Excluded authority |
|---|---|---|
| Development apply | Development top-level folder | Staging, production, and foundation |
| Staging apply | Staging top-level folder | Development, production, and foundation |
| Production apply | Production top-level folder | Development, staging, and foundation |
| Foundation apply | Organization and shared control surfaces | Environment workload mutation unless explicitly delegated |

The unit also publishes `environment_apply_authority`, normal-plane supply-chain service accounts,
and the non-secret signer identity contract consumed by `github-config`. Treat output names as an
interface: coordinate consumers before renaming them.

## Review and validation

Review folder IDs and service-account emails against bootstrap outputs; mock outputs are valid only
for `plan`, `validate`, and `init`. Run `nix develop .#ci --command make validate`, inspect the exact
saved plan, and verify that every grant is inherited from only its intended folder. See
[automation identity handoff](../../docs/automation-identity-handoff.md) for the cross-repository
activation sequence.
