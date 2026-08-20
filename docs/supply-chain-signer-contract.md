<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

# Supply-chain signer contract

The artifact builder cannot authorize its own output for production. Buildkite issues a
build attestation, a separate Buildkite qualifier issues the qualification attestation, and
the protected GitHub release workflow verifies both before creating the distinct deployment
attestation.

## Trust and output handoff

| Variable | Authoritative output |
|---|---|
| `WIF_PROVIDER_SIGNER` | `bootstrap.artifact_signer_wif_provider` |
| `ARTIFACT_SIGNER_PRINCIPAL` | `bootstrap.artifact_signer_principal` |
| `ARTIFACT_SIGNER_JOB_WORKFLOW_REF` | `bootstrap.artifact_signer_job_workflow_ref` |
| `SA_ARTIFACT_SIGNER` | `1-org/automation-iam.artifact_signer_identity_contract` |
| `BINAUTHZ_BUILD_ATTESTOR_PROJECT` | Applied Buildkite build-attestor module output |
| `BINAUTHZ_BUILD_ATTESTOR` | Applied Buildkite build-attestor module output |
| `BINAUTHZ_QUALIFICATION_ATTESTOR_PROJECT` | Applied qualification-attestor module output |
| `BINAUTHZ_QUALIFICATION_ATTESTOR` | Applied qualification-attestor module output |
| `BINAUTHZ_DEPLOYMENT_ATTESTOR_PROJECT` | Applied production deployment-attestor module output |
| `BINAUTHZ_DEPLOYMENT_ATTESTOR` | Applied production deployment-attestor module output |
| `BINAUTHZ_DEPLOYMENT_ATTESTOR_KEY_VERSION` | Applied production deployment-attestor module output naming one immutable key version |

`bootstrap` enforces the immutable organization/repository IDs, exact `release` environment
subject, exact audience, and exact
`mindclade/.github/.github/workflows/reusable-binauthz-sign.yml@refs/tags/v3.0.0`
`job_workflow_ref`. `infrastructure-live` binds that one exported principal to the signer
service account. Do not replace it with a repository-wide principal set.

The private `binauthz` module is not present in this checkout, so its concrete output names
remain **Unknown**. Do not construct a key-version path, assume version `1`, or publish values
from comments/mocks. Before activation, the module must publish the seven attestor fields
above, pass the exact-ref interface preflight, and produce a reviewed credentialed plan.

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

## Required negative tests

Before publishing the variables to the monorepo, prove that:

- the builder cannot impersonate the signer service account;
- the builder cannot read or use qualification/deployment signing keys;
- the builder cannot attach to the deployment attestor note or create an attestation;
- the qualifier cannot attach to the build or deployment notes or use their keys;
- the signer cannot exchange a token outside the monorepo `release` environment;
- the signer cannot exchange a token from any workflow other than the exact immutable
  reusable signer workflow;
- a digest missing either Buildkite build or independent qualification evidence is rejected; and
- the qualifier cannot create the deployment attestation.

Retain the negative authorization evidence with the critical trust-change record.
