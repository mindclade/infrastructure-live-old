<!-- mindclade-doc: changelog@1 -->

# Mindclade changelog · live infrastructure

This file records material repository changes from the adoption of the
estate-wide changelog contract. Earlier history remains available in Git and is
not reconstructed or relabeled here.

## Unreleased

### Added

- Added the source-only common-CI Bazel-cache foundation: separate reader/writer identities,
  exact bootstrap `1.5.0` route bindings, CMEK and access-logged storage, and protected foundation
  scope selection. The applied-output exporter now emits the combined exact `1.4.0` handoff only
  after its Terraform output matches the bootstrap identity JSON. Activation remains blocked on
  the unpublished `v0.4.0` module and qualified create-only client semantics.
- Added the source-only private Nix binary-cache foundation: dedicated create-only GCS backend,
  server-only secret containers, zero-replica Attic source, protected population workflow
  contract, stable redacted validation codes, and an explicit proposed → qualifying → qualified
  → activated lifecycle. No substituter, public key, endpoint, secret value, or write caller is
  activated.
- Added the exact estate-wide `LEGAL.md` reliance policy and made it part of
  the repository contract.

### Changed

- Updated the proprietary license with the protected-disclosure notice and
  recorded the Contributor Covenant 2.1 attribution and modifications.
- Moved the reusable SPDX source-header template under `.github/` so `LICENSE`
  is the sole root license surface.

### Fixed

### Security

- Bound every runtime state-bucket and Terraform service-account value to one versioned,
  schema-validated record generated from the applied bootstrap contract and its clean source
  commit. Mismatches now fail closed with redacted diagnostics before connected automation can
  authenticate.
- Clarified that security response times are non-contractual operational
  targets and that safe harbor cannot authorize third-party systems or
  unlawful conduct.

### Removed

## 2026-08-21 — Common-document governance baseline

### Added

- established local, versioned contribution, security, support, conduct,
  governance, license, notice, and changelog documents;
- added machine-enforced presence and content requirements for those documents.

### Changed

- aligned the root documentation with the Mindclade MONO brand and repository
  authority contract;
- standardized proprietary rights, contributor authorization, third-party
  precedence, and support routing across the governed repository estate.

### Security

- made private vulnerability reporting and the absence of a published PGP key
  explicit;
- prohibited secrets, sensitive evidence, customer data, model material, and
  restricted biological content in public or general-purpose channels.
