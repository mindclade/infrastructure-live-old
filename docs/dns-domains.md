<!-- mindclade-doc: reference@1 -->

# Mindclade domain portfolio and DNS ownership

> **Audience:** DNS, platform, and security operators.
> **Outcome:** change domain delegation without losing web, identity, or mail service.

Squarespace remains the registrar. Google Cloud DNS is the authoritative DNS provider after
a controlled per-domain delegation.

| Domain | Role | Mail policy |
|---|---|---|
| `mindclade.com` | company, identity, email, trust | mail-enabled; import existing MX/SPF/DKIM/DMARC before delegation |
| `mindclade.ai` | production product, API, console, authentication | no-mail until explicitly changed |
| `mindclade.dev` | developer documentation, SDKs, schemas | no-mail until explicitly changed |
| `mindclade.studio` | demos, playgrounds, isolated experiments | no-mail until explicitly changed |

The four apex zones are owned by `3-networks/shared/public-zones`. Kubernetes Gateway/Ingress
objects remain in `gitops`; application host configuration remains in the monorepo. Do not
grant ExternalDNS write access to an apex zone. Delegate a narrow environment subzone first.

The reusable, environment-neutral DNS module remains in
`mindclade-internal-monorepo/infra/terraform/modules/dns`; this repository consumes only an
immutable release. The module, its tests, and its Terraform CI fixtures do not move into the
live-state repository.

## Current activation gate

The normalized inventory in
[`contracts/dns-domain-inventory.json`](../contracts/dns-domain-inventory.json)
marks all four domains as blocked pending review. The committed `mindclade.com` record map in
[`3-networks/shared/public-zones/mindclade-com/terragrunt.hcl`](../3-networks/shared/public-zones/mindclade-com/terragrunt.hcl)
is currently empty. **Do not change registrar nameservers or DNSSEC delegation** until every
authoritative web, identity, mail, verification, and security record has been inventoried,
reviewed, and applied to Cloud DNS. An empty managed zone is not a delegation-ready zone.

The current live units still use the legacy `domain` zone input while the released module
requires `dns_name`, and the current release does not support several record types on one
owner through distinct map identifiers. The inventory carries explicit activation blockers
for both interface gaps until the live input is aligned and an immutable module release
includes the reviewed `name` override. Do not point a live unit at a branch or an unpublished
tag to bypass those gates.

## Automated controls

Static validation runs locally and in pull-request CI:

```sh
python3 scripts/validate_dns_portfolio.py
python3 scripts/validate_dns_portfolio.py --require-ready mindclade.studio
```

The first command validates roles, ownership, DNSSEC, record types, no-mail controls, module
release compatibility, and parity between the normalized inventory and live Terragrunt
records. The second additionally fails unless the selected domain is explicitly ready.

The manually dispatched **DNS cutover check** workflow is read-only. Its `preflight` phase
compares every inventoried record on the incumbent and Cloud DNS nameservers. Its
`postcutover` phase checks public delegation and records, with an optional DS/DNSKEY presence
gate after DNSSEC is re-established. It uploads a timestamped JSON artifact and has no
registrar or cloud write identity. Follow the
[Cloud DNS delegation runbook](runbooks/dns-delegation.md) for the manual Squarespace steps,
mail tests, evidence, and rollback order.

## Delegate a domain

1. Export the current authoritative zone and independently inventory apex, `www`, identity,
   MX, SPF, DKIM, DMARC, CAA, verification, and service records.
2. Add the reviewed records to the appropriate Terragrunt unit. Preserve mail TTLs and semantics;
   do not synthesize missing values.
3. Apply through the protected infrastructure workflow and record the Cloud DNS nameservers.
4. Query each new authoritative nameserver directly and compare answers with the incumbent zone.
5. Lower incumbent TTLs far enough in advance for cached answers to expire.
6. Disable or replace the old DNSSEC chain according to the registrar change plan; stale DS
   records can make the entire domain unreachable.
7. Change nameserver delegation at Squarespace during the approved window.
8. Verify public resolution, web, identity, mail delivery, and negative/no-mail policy from
   multiple external resolvers.
9. After stable propagation, publish the Cloud DNS DS record at Squarespace and verify DNSSEC.

Useful read-only checks:

```sh
gcloud dns record-sets list --zone '<managed-zone-name>'
dig @'<cloud-dns-nameserver>' mindclade.com SOA
dig mindclade.com NS
dig mindclade.com MX
```

## Rollback

Keep the incumbent zone unchanged through the rollback window. If critical answers fail before
DNSSEC is re-established, restore the previous registrar nameservers and DS state using the
approved change record, then verify cached and authoritative responses. Preserve query output,
timestamps, resolver locations, and registrar audit evidence.
