<!-- mindclade-doc: support@1 -->

# Mindclade support · `infrastructure-live`

| Document control | Value |
| --- | --- |
| Owner | Mindclade Platform |
| Version | 1.0 |
| Last reviewed | August 21, 2026 |

## Routing

| Need | Route |
| --- | --- |
| Infrastructure code or documentation defect | Open a sanitized issue in this repository |
| Planned infrastructure change | Open a pull request with plan evidence required by [CONTRIBUTING.md](CONTRIBUTING.md) |
| Production incident | Use the owning [runbook index](docs/runbooks/README.md) and incident-response process |
| DNS change or delegation | Follow [docs/dns-domains.md](docs/dns-domains.md) and its cutover runbook |
| Security vulnerability, state exposure, or identity defect | Follow [SECURITY.md](SECURITY.md); never open an issue |
| Ring-0 state or federation problem | Route to `mindclade/bootstrap` |
| Contractual customer support | Use the channel and service terms in the applicable agreement |

GitHub issues do not carry an SLA. Never attach raw Terraform state or plans,
credentials, customer data, private model material, restricted biological
content, or incident-sensitive evidence. Use sanitized resource identifiers,
workflow-run links, and evidence digests.

The applicable customer agreement or incident-response process controls if it
conflicts with this routing guide.

