<!-- mindclade-doc: reference@1 -->

# Authoritative DNS project boundary

> **Purpose:** prevent duplicate ownership of the shared Cloud DNS project.

The actual `mc-common-dns` project is created once by `1-org/common-projects`. Public and
private DNS zone units depend on that state directly. This directory records the shared
networking boundary and must not create a duplicate project.

## Invariants

- `1-org/common-projects` is the only unit that creates `mc-common-dns`.
- Public and private zone units consume the project ID through declared Terragrunt dependencies.
- This boundary must not contain a second project resource or independent project state.
- Apex delegation remains blocked until the committed zone data is complete and verified.

Validate changes with `nix develop .#ci --command make validate` and review the resolved dependency
graph before applying a DNS unit. See [domain portfolio and DNS ownership](../../../docs/dns-domains.md)
for zone ownership, delegation gates, verification, and rollback.
