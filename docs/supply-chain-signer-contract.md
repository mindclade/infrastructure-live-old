<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

# Supply-chain signer contract

The artifact builder cannot authorize its own output for production. A capability-isolated ARC
builder issues the build attestation, a separate ARC qualifier issues the qualification
attestation, and the protected GitHub release workflow verifies both before creating the
distinct deployment attestation.

## Trust and output handoff

| Variable | Authoritative output |
|---|---|
| `ARTIFACT_RELEASE_IDENTITIES_JSON` | `bootstrap.platform_contract.github.artifact_release_identities` |
| `WIF_PROVIDER_ARC_*` / `WIF_PROVIDER_SIGNER` | the corresponding bootstrap capability identity |
| `SA_ARC_CANARY` / `SA_ARTIFACT_*` | `1-org/automation-iam.artifact_release_identity_contract` |
| `BINAUTHZ_BUILD_ATTESTOR_PROJECT` | `5-workloads/production/binary-authorization.project_id` |
| `BINAUTHZ_BUILD_ATTESTOR` | `5-workloads/production/binary-authorization.attestor_names["build-attestor"]` |
| `BINAUTHZ_QUALIFICATION_ATTESTOR_PROJECT` | `5-workloads/production/binary-authorization.project_id` |
| `BINAUTHZ_QUALIFICATION_ATTESTOR` | `5-workloads/production/binary-authorization.attestor_names["qualification-attestor"]` |
| `BINAUTHZ_DEPLOYMENT_ATTESTOR_PROJECT` | `5-workloads/production/binary-authorization.project_id` |
| `BINAUTHZ_DEPLOYMENT_ATTESTOR` | `5-workloads/production/binary-authorization.attestor_names["deployment-attestor"]` |
| `BINAUTHZ_DEPLOYMENT_ATTESTOR_KEY_VERSION` | `5-workloads/production/binary-authorization.attestor_key_versions["deployment-attestor"]` |

`bootstrap` enforces immutable organization/repository IDs, exact audiences, trusted-main caller,
push-only execution, and an exact v4 reusable workflow for every capability. Each non-signer
provider maps a capability-prefixed `google.subject`, preventing cross-provider subject
collisions. `infrastructure-live` binds each exported principal only to its matching normal-plane
service account. Do not replace these bindings with a repository-wide principal set.

The private `binauthz` module publishes `project_id`, `attestor_names`, and
`attestor_key_versions`. The live pin must reference an immutable released module revision
containing those outputs and the create/get/list-only occurrence contract. Do not construct a
project, service-account email, attestor name, or key-version path; do not assume key version
`1`; and never publish comments, mocks, plan placeholders, or sensitive outputs.

After all three owning units are applied, run
`scripts/export-applied-control-plane-handoff.py`. The exporter reads only the exact
`1-org/automation-iam`, `5-workloads/shared/control-plane-identities`, and
`5-workloads/production/binary-authorization` state outputs. It verifies the bootstrap signer
tuple, blocking production enforcement, exact attestor names, immutable KMS key version, clean
source SHA, and non-sensitive/non-mock values, then writes a mode-0600 JSON contract outside
the repository. `github-config` consumes that file and must not accept free-form replacements.

`qualification-attestor` includes vulnerability/security analysis and numerical/release
qualification. It replaces the ambiguous `vuln-scan-attestor`; vulnerability is not a fourth
deployment authority. Global production admission consumes only `deployment-attestor`, whose
issuer verified both upstream attestations. GitOps verifies that same deployment trust root.
`biosecurity-review-attestor` is reserved for an explicit restricted-biological workload or
namespace policy and is not part of the global default.

## Minimum signer permissions

| Capability | Scope |
|---|---|
| Builder | Artifact publication plus create/list on `build-attestor`; its note/key only |
| Qualifier | Artifact and analysis read plus create/list on `qualification-attestor`; its note/key only |
| Protected signer | Artifact read; cryptographic verification of all three attestors; create/list on `deployment-attestor`; its note/key only |

The project-local `mindcladeAttestationOccurrenceCreator` custom role includes only occurrence
create/get/list and project discovery; it deliberately omits occurrence update/delete. All
of those permissions are supported in Google Cloud custom roles. Note-scoped
`roles/containeranalysis.notes.attacher` and key-scoped `roles/cloudkms.signerVerifier`
remain owned by the Binary Authorization module. No issuer is an attestor, note, key, or
policy administrator, and each note/key grant must name only its matching identity. Occurrence
read is project-scoped; attachment and signing mutation remain stage-scoped by note and key.
Issuers and GitOps verification use the read-only
`roles/binaryauthorization.attestorsVerifier`; the list-only `attestorsViewer` role cannot
prove an occurrence signature and is insufficient for promotion or deployment evidence.
The GitOps verifier also holds read-only `roles/binaryauthorization.policyViewer` in each
platform project so it can prove the applied production default, attestor, and exact Argo digest
exceptions. It has no policy mutation role.

## Required negative tests

Before publishing the variables to the monorepo, prove that:

- the canary, builder, qualification reader, qualifier, signer, and promoter cannot impersonate
  one another;
- the builder cannot read or use qualification/deployment signing keys;
- the builder cannot attach to the deployment attestor note or create an attestation;
- the qualifier cannot attach to the build or deployment notes or use their keys;
- the signer cannot exchange a token outside the monorepo `release` environment;
- the signer cannot exchange a token from any workflow other than the exact immutable
  reusable signer workflow;
- a digest missing either ARC build or independent qualification evidence is rejected; and
- the qualifier cannot create the deployment attestation.

Retain the negative authorization evidence with the critical trust-change record.
