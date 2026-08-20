<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

# Binary Authorization blocked a deployment

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
