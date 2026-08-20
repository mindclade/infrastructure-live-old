<!-- mindclade-doc: reference@1 -->

# Protected disaster-recovery evidence archive

This state owns the seven-year US multi-region DR evidence bucket. Its sibling access-log state
owns the separately protected server-access log bucket, `1-org/kms-dr-evidence` owns the US
multi-region-compatible HSM key, and `1-org/automation-iam` owns the keyless writer identity.

The writer receives only bucket-level object creator and viewer roles. Every workflow upload also
uses a generation-zero precondition; neither IAM nor the client permits overwrite, deletion,
retention administration, or bucket administration. Both buckets enable versioning, public-access
prevention, uniform access, 90-day soft delete, deletion protection, Terraform prevent-destroy,
and a locked 2,555-day retention policy.

Activation is deliberately protected and irreversible. Before the first apply, verify the exact
project and bucket names, storage service-agent KMS grant, legal/cost approval, access-log delivery,
WIF principals, and GitHub environment reviewers. Export the following non-secret values into each
caller's protected `scratch` and `staging` GitHub environments:

- `WIF_PROVIDER_DR_EVIDENCE` and `SA_DR_EVIDENCE_WRITER` from
  `dr_evidence_identity_contract`;
- `DR_EVIDENCE_PROJECT` from the common security project output;
- `DR_EVIDENCE_BUCKET` from this module's bucket output.

No local validation or source file claims that the retention lock, WIF exchange, or evidence write
has occurred. Prove those only through an approved connected scratch drill.
