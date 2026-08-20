# Control-plane identities

This live-only unit is the narrow handoff from bootstrap-managed GitHub federation to
normal non-Ring-0 GitOps services. It creates the GitOps render and verifier service
accounts, one CMEK-protected Secret Manager **container** for the render GitHub App key,
and least-privilege read bindings. It never creates a secret version.

The private Terraform module-reader secret is intentionally absent: its empty secret
container is owned by `bootstrap`, because infrastructure-live must read private modules
before this normal security project exists.

After this unit applies, an authorized operator adds the render GitHub App private-key
version to `github-app-render-pem` through the audited secret-rotation runbook. The GitHub
App ID is a non-secret repository variable managed by `github-config`.
