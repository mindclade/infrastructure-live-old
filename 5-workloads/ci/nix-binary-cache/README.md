# Common CI Nix binary-cache backend

This foundation-owned unit declares the private, CMEK-encrypted, versioned GCS backend proposed
for Attic. It reuses the retention-locked shared cache access-log bucket with a distinct prefix
and grants only `roles/storage.objectCreator` plus `roles/storage.objectViewer` to the dedicated,
non-federated `nix-cache-storage` account. No identity receives object-admin access.

The module's `substituter_uri` and trusted public key remain null. Raw GCS is not a Nix cache
service, and the module's HTTPS/GS outputs identify storage only. Current Attic uses the S3 API;
GCS interoperability requires HMAC credentials and Attic can issue ordinary or multipart writes
without generation preconditions. Terraform must not create the HMAC key because its secret would
enter state. Automatic and manual Attic garbage collection remain forbidden because the backend
identity cannot delete objects.

Do not apply this unit until reusable module `v0.4.0` is published from the reviewed commit and a
credentialed saved plan is approved. Do not activate a client or server until duplicate uploads,
multipart aborts, overwrite/delete denial, presigned reads, HMAC rotation/revocation, KMS/logging,
database/signing restore, cold/warm builds, tamper rejection, cache loss, and cost are qualified.
The flake-locked client and proposed server image currently use different upstream commits, so
their exact API, retry, and upload compatibility is a named blocker rather than an assumption.
Rollback removes every client substituter before scaling Attic down; retained storage is a
separate reviewed lifecycle decision.
