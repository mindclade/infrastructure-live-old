<!-- mindclade-doc: reference@1 -->

# Control-plane identities

> **Purpose:** hand bootstrap-managed GitHub federation to normal-plane GitOps render and verifier
> identities without moving secret payloads into Terraform.

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

## Published interface

| Output | Consumer | Content |
|---|---|---|
| `service_accounts` | Platform operators | Render and verifier service-account emails |
| `github_config_identity_handoff` | `github-config` | `SA_GITOPS_RENDER` and `SA_GITOPS_VERIFIER` |
| `secret_resource_names.render` | Authorized secret operator | Empty `github-app-render-pem` container name |

## Activate and verify

1. Apply the exact reviewed unit plan through the foundation protected environment.
2. Reapply `github-config` so the published non-secret service-account values reach their governed
   consumers.
3. Add the GitHub App private key as an out-of-band Secret Manager version; never print or pass the
   payload through Terraform.
4. Verify the render identity can read only its installed repositories and secret, and the verifier
   can read only required evidence. Retain negative authorization results for unrelated resources.

Run `nix develop .#ci --command make validate` before review. Follow the full
[automation identity handoff](../../../docs/automation-identity-handoff.md) for sequencing and
rollback.
