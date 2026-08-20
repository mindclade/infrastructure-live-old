<!-- mindclade-doc: runbook@1 -->

# Restore Cloud SQL into an isolated target

Owner: Database service owner with a cloud-platform primary and a distinct observer. Restore always
creates an isolated scratch or staging target first; this runbook does not authorize an in-place
production restore.

## Trigger and safety boundary

Use this procedure for deletion, corruption, failed migration, or a recovery drill. Freeze writers,
record the incident/drill start and desired recovery point, and preserve instance, backup, PITR,
replica, KMS, network, and audit metadata. Abort if the source project/instance is ambiguous, the
selected recovery point is outside retention, keys are unavailable, or any command targets the
source instance for deletion or overwrite.

## Read-only diagnosis

1. List backups and PITR coverage; select the newest recovery point before corruption.
2. Capture source engine/version/flags, private-network attachment, KMS key version, database size,
   replication lag, and application compatibility requirements.
3. Produce and review Terraform for a uniquely named isolated target with no production traffic.
4. Estimate restore time and capacity before protected approval.

## Restore and validate

An authorized operator may create the isolated instance and run the documented Cloud SQL restore or
PITR operation after environment approval. Keep application credentials and routing disabled until
database integrity checks, schema/version checks, row-count/checksum samples, and security controls
pass. Point only a staging validation client at the restored endpoint.

Success requires the selected recovery point to be present, integrity/application probes to pass,
encryption/private connectivity/audit logging to match policy, and no source mutation. Measure RPO
from the selected recovery point and RTO through completed validation. Preserve command output and
query summaries without sensitive row data, hash the evidence, record corrective actions, and set
the next drill date in report v2. Promotion or production traffic cutover requires a separate
incident decision and change approval.
