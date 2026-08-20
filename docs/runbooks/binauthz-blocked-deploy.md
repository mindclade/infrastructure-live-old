<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

<!-- mindclade-doc: runbook@1 -->

# Binary Authorization blocked a deployment

> **Use when:** GKE rejects an immutable image digest under Binary Authorization policy.
> **Impact:** the new revision is blocked; the last healthy qualified revision should remain.
> **Primary owner:** release owner with platform and security support.
> **Escalate:** immediately if an expected attestation cannot be verified or policy/key drift exists.

## Symptoms

GKE admission rejects a digest with a Binary Authorization message stating that one or more
required attestations cannot be verified.

## Impact

The new workload revision does not start. A healthy previous revision should remain; do not
weaken admission merely to make the rollout progress.

## Diagnosis

1. Record the exact immutable image digest, environment, policy decision, and missing
   attestor name from the admission/audit event.
2. Trace the digest to its source commit, SBOM/provenance, independent qualification, signer
   run, GitOps commit, and expected attestor/key version.
3. With a read-only incident identity, verify the attestation is attached to the approved
   attestor note and matches the digest. Verify the KMS public key version is enabled and is
   the version configured by the protected release workflow.
4. If an attestation exists but cannot be verified, treat key, note, project, or policy drift
   as a critical control-plane incident.

## Resolution

1. Fix or rerun the failed qualification/signing stage for the same digest through the
   protected release environment, or revert the GitOps reference to a previously qualified
   digest.
2. Do not create an attestation manually with a human or builder identity.
3. Do not add an `ALWAYS_ALLOW` rule or mutable image exception. A true emergency exception
   needs a critical change record, exact scope, expiry, two qualified approvals, and
   immediate removal after containment.
4. Confirm GKE admits the exact digest and preserve the resulting audit linkage.

## Prevention

Keep builder negative-authorization tests and a staging end-to-end attestation test in the
release qualification suite.

## Verify recovery

- GKE admits the exact qualified digest without a policy exception.
- The attestation resolves to the approved note and enabled KMS key version.
- GitOps reports the intended revision healthy and synchronized.
- The incident/change record links source, SBOM, provenance, qualification, signer, GitOps, and
  admission evidence.

If those links cannot be proven, keep the deployment blocked and hand off the digest, attestor,
policy decision, key version, timestamps, and relevant audit events to security.

## Escalation and handoff

Escalate unverifiable evidence or key/policy drift to security with the exact digest, environment,
attestor note, KMS key version, policy decision, source/release commits, signer run, timestamps, and
audit events. Do not attach secret values or grant an admission exception for diagnosis.
