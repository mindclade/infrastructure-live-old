# Environment automation IAM

Bootstrap creates the keyless identities but does not own normal environment hierarchy or
infrastructure policy. This foundation unit performs the one-way handoff by granting each
apply identity permissions inherited only within its own top-level environment folder.

The foundation identity remains the sole automation authority for organization policy,
centralized security/logging, shared DNS/networking, and cross-environment controls. Plan
uses a separate read-only identity. No human credential or service-account key is created.
