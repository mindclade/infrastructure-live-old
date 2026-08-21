<!-- mindclade-doc: reference@1 -->

# Protected production qualification archive

This state owns the append-only, seven-year production qualification archive. Its sibling state
owns the access-log bucket, the evidence KMS state owns the dedicated HSM key, and the
control-plane identity state owns separate keyless source-reader and archive-writer identities.

The writer has only bucket-level object creator and viewer roles. The protected workflow must use
generation-zero preconditions for every upload. Neither identity can delete, overwrite, administer
retention, or administer the bucket. Both buckets use CMEK, uniform access, public-access
prevention, versioning, 90-day soft delete, deletion protection, Terraform prevent-destroy, and a
locked 2,555-day retention policy.

No source check proves the lock, WIF exchange, upload, or reviewer access. Retain those results as
connected production evidence and never archive state, plans, credentials, tokens, kubeconfigs, or
sensitive payloads.
