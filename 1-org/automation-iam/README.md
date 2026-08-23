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
and the non-secret signer identity contract consumed by `github-config`. It owns separate common-CI
`bazel-cache-reader` and `bazel-cache-writer` accounts and binds the exact bootstrap `2.0.0` route
principals without granting bucket IAM here. The stable cache handoff exposes
`WIF_PROVIDER_BAZEL_CACHE`, `SA_BAZEL_CACHE_READER`, and `SA_BAZEL_CACHE_WRITER`; the cache module
owns object access and KMS owns the storage-service-agent key grant. Treat output names as an
interface: coordinate consumers before renaming them.

Bootstrap contract `2.0.0` also hands off one exact workstation-image publication principal.
This unit creates `workstation-image-pub`, binds only that principal, and grants no project role.
`5-workloads/ci/workstation-image-source` owns its create-only object permission. The applied
`workstation_image_identity_contract` is authoritative for
`WIF_PROVIDER_WORKSTATION_IMAGE` and `SA_WORKSTATION_IMAGE_BUILDER`; GitHub may publish the raw
disk but cannot create or select a Compute Image.

The unit also owns `nix-cache-storage`, a separate deletion-protected service account used only
by the proposed private Attic backend bucket. It has no GitHub WIF binding and no project role.
The Nix cache module grants bucket-scoped create/read access. Terraform must never create a
`google_storage_hmac_key`: the secret would enter state. HMAC issuance, rotation, revocation, and
Secret Manager version writes remain out-of-band protected operations after qualification.

## Review and validation

Review folder IDs and service-account emails against bootstrap outputs; mock outputs are valid only
for `plan`, `validate`, and `init`. Run `nix develop .#ci --command make validate`, inspect the exact
saved plan, and verify that every grant is inherited from only its intended folder. See
[automation identity handoff](../../docs/automation-identity-handoff.md) for the cross-repository
activation sequence.
