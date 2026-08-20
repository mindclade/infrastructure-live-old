<!-- mindclade-doc: reference@1 -->

# Partner project intake

> **Purpose:** define the evidence required before a partner receives infrastructure authority.

Partner infrastructure is instantiated only after an approved partner identifier, owner, data
classification, isolation model, expiration/review date, and security review exist. Each partner
receives dedicated project, identity, secret, network, and storage boundaries. Generic modules
must not embed partner names.

## Required intake

| Field | Requirement |
|---|---|
| Partner ID | Stable, non-secret identifier approved for resource naming |
| Owner | Accountable Mindclade team and operational escalation path |
| Data classification | Approved classification and residency/retention constraints |
| Isolation model | Dedicated network, project, identity, secret, and storage boundaries |
| Lifecycle | Activation date, review date, expiration, and offboarding owner |
| Security review | Linked approval covering access, data flow, and incident obligations |

Copy `partner.hcl.example` only into an approved partner directory and replace every example value.
Do not place partner secrets, customer data, or contract content in live configuration. Run
`nix develop .#ci --command make validate`, review the exact saved plan, and satisfy the
[production activation gates](../../docs/production-activation-gates.md) before apply.
