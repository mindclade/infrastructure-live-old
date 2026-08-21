<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

# Supply-chain signer contract

The artifact builder cannot authorize its own output for production. The target design uses a
builder attestation, an independently issued qualification attestation, and a protected GitHub
deployment attestation. In the current quarantine, Buildkite federation and the first two issuers
are disabled, the retained v3 signer is the only issuer binding, and every Binary Authorization
policy is audit-only. No production release authority is claimed.

## Trust and output handoff

| Variable | Authoritative output |
|---|---|
| `WIF_PROVIDER_SIGNER` | `bootstrap.artifact_signer_wif_provider` |
| `ARTIFACT_SIGNER_PRINCIPAL` | `bootstrap.artifact_signer_principal` |
| `ARTIFACT_SIGNER_JOB_WORKFLOW_REF` | `bootstrap.artifact_signer_job_workflow_ref` |
| `SA_ARTIFACT_SIGNER` | `1-org/automation-iam.artifact_signer_identity_contract` |
| `BINAUTHZ_BUILD_ATTESTOR_PROJECT` | `5-workloads/production/binary-authorization.project_id` |
| `BINAUTHZ_BUILD_ATTESTOR` | `5-workloads/production/binary-authorization.attestor_names["build-attestor"]` |
| `BINAUTHZ_QUALIFICATION_ATTESTOR_PROJECT` | `5-workloads/production/binary-authorization.project_id` |
| `BINAUTHZ_QUALIFICATION_ATTESTOR` | `5-workloads/production/binary-authorization.attestor_names["qualification-attestor"]` |
| `BINAUTHZ_DEPLOYMENT_ATTESTOR_PROJECT` | `5-workloads/production/binary-authorization.project_id` |
| `BINAUTHZ_DEPLOYMENT_ATTESTOR` | `5-workloads/production/binary-authorization.attestor_names["deployment-attestor"]` |
| `BINAUTHZ_DEPLOYMENT_ATTESTOR_KEY_VERSION` | `5-workloads/production/binary-authorization.attestor_key_versions["deployment-attestor"]` |

`bootstrap` enforces the immutable organization/repository IDs, exact `release` environment
subject, exact audience, and exact
`mindclade/.github/.github/workflows/reusable-binauthz-sign.yml@refs/tags/v3.0.0`
`job_workflow_ref`. `infrastructure-live` binds that one exported principal to the signer
service account. Do not replace it with a repository-wide principal set.

The private `binauthz` module publishes `project_id`, `attestor_names`, and
`attestor_key_versions`. The live pin must reference an immutable released module revision
containing those outputs and the create/get/list-only occurrence contract. Do not construct a
project, service-account email, attestor name, or key-version path; do not assume key version
`1`; and never publish comments, mocks, plan placeholders, or sensitive outputs.

After all three owning units are applied, run
`scripts/export-applied-control-plane-handoff.py`. The exporter reads only the exact
`1-org/automation-iam`, `5-workloads/shared/control-plane-identities`, and
`5-workloads/production/binary-authorization` state outputs. It verifies the bootstrap signer
tuple, audit-only production posture, exact attestor names, immutable KMS key version, clean
source SHA, and non-sensitive/non-mock values, then writes a mode-0600 JSON contract outside
the repository. `github-config` consumes that file and must not accept free-form replacements.

`qualification-attestor` includes vulnerability/security analysis and numerical/release
qualification. It replaces the ambiguous `vuln-scan-attestor`; vulnerability is not a fourth
deployment authority. Global production admission consumes only `deployment-attestor`, whose
issuer verified both upstream attestations. GitOps can inventory that same deployment trust root,
but cannot treat it as active admission while the exported posture remains audit-only.
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
