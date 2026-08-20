<!-- mindclade-doc: runbook@1 -->

# Restore a protected Cloud Storage bucket

Owner: Data service owner with a cloud-platform primary and a distinct observer. Recovery copies a
known version into a new scratch or staging destination; it never overwrites or relaxes the source.

## Trigger and no-go conditions

Use object-version and audit evidence to respond to deletion, corruption, encryption failure, or a
drill. Record the source bucket/project, object prefix, incident time, retention/lock state, KMS key,
and exact source revisions. Abort if the source is not versioned as expected, the recovery generation
is ambiguous, retention or legal hold would be changed, or a command can delete/overwrite source
objects.

## Read-only diagnosis

1. Enumerate affected object names, generations, timestamps, hashes, storage class, holds, and KMS
   metadata without downloading sensitive contents unnecessarily.
2. Identify the latest verified generation before corruption and calculate observed data loss.
3. Verify a separately named destination with equivalent location, encryption, access, logging, and
   retention controls. Review the exact copy manifest.

## Restore and validate

After protected approval, copy explicit source generations to the isolated destination using
destination generation-match-zero preconditions. Never use wildcard deletion, retention changes,
or an in-place rewrite. Compare object counts, sizes, CRC32C/MD5 where applicable, metadata, KMS,
IAM, and application-level samples. Keep production routing unchanged.

Success requires every manifest entry to match, source generations and controls to remain unchanged,
destination access to be least privilege, and staging application validation to pass. Record measured
RPO/RTO, operator identities, copy manifest and command output hashes, failures, corrective actions,
and next drill date in report v2. A production cutover is a separate approved change.
