# Nix cache secret containers

This unit creates only four deletion-protected Secret Manager containers: Attic's server JWT key,
database URL, and the paired GCS XML API HMAC values. The reusable module never accepts a payload
or creates a secret version, so plaintext cannot enter Terraform configuration, plans, state, or
logs. No GitHub principal is an accessor.

The declared direct Workload Identity principal names a future `mindclade-cache/attic-secret-sync`
service account. No active GitOps source creates that account or SecretSync object, and the
zero-replica monorepo server source references an absent Kubernetes Secret. Apply creates no
usable server credential path by itself.

HMAC creation is a protected out-of-band operation because Google returns the secret only once.
Qualify paired rotation, staged version enablement, SecretSync, access-deny alerts, database
credential rollover, JWT/token revocation, emergency recovery, audit retention, and HMAC
deactivation before writing versions. The cache's Nix signing material remains server-managed
and must be covered by the independently restored database/evidence procedure.
