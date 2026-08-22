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

The target Cloud DNS project is `mc-common-dns`. Production service names use
`<service>.mindclade.ai`; staging and development use `<service>.staging.mindclade.ai` and
`<service>.dev.mindclade.ai`. Production wildcard DNS records are forbidden. The Gateway and
route consumers now use that explicit boundary, and each environment has a separate private
service-zone composition attached only to its own VPC and pointing at its own reserved Gateway
VIP. These are source contracts, not evidence that any zone, VIP, or route is live.

Certificate ownership belongs to this repository through Google Certificate Manager. The
v0.4.0 candidate creates regional `PER_PROJECT_RECORD` authorizations and one generated public
CNAME for every exact SAN, plus three stable certificate names per environment project. CAA is
now declared in the blocked target inventory, and the Gateway source attaches those stable
Certificate Manager names. None of those resources has been applied, the complete issuer
inventory is not yet approved, and the three certificate-serving domains retain explicit
activation blockers. cert-manager remains only for in-cluster operator webhook PKI; it is not an
edge certificate owner.

The reusable, environment-neutral DNS module remains in
`mindclade-internal-monorepo/infra/terraform/modules/dns`; this repository consumes only an
immutable release. The module, its tests, and its Terraform CI fixtures do not move into the
live-state repository.

## Current activation gate

The normalized inventory in
[`contracts/dns-domain-inventory.json`](../contracts/dns-domain-inventory.json)
marks all four domains as blocked pending review. The committed `mindclade.com` record map in
[`3-networks/shared/public-zones/mindclade-com/terragrunt.hcl`](../3-networks/shared/public-zones/mindclade-com/terragrunt.hcl)
preserves the legacy Google MX set, Google verification TXT record, and 2048-bit
`google._domainkey` DKIM value observed through a read-only Admin-console and public-DNS
inventory on 2026-08-21. It also declares the reviewed final Google-only hard-fail SPF and
DMARC reject targets. Cloudflare remains authoritative through `cleo.ns.cloudflare.com` and
`rosa.ns.cloudflare.com`; the public zone did not serve those SPF or DMARC targets during the
read-only observation. Their presence in desired source is not connected evidence, so the
inventory remains incomplete and explicitly blocked on mail-authentication observation, sender
review, and an independent full incumbent-zone review. **Do not change registrar nameservers or
DNSSEC delegation** until every authoritative web, identity, mail, verification, and security
record has been inventoried, reviewed, and applied to Cloud DNS. A partially inventoried managed
zone is not a delegation-ready zone.

The same read-only checks found the exact incumbent Squarespace apex `A` set and `www` CNAME on
`mindclade.ai` and `mindclade.dev`. Schema v3 retains only those reviewed records through the
exact `apex-a` and `www-cname` map-key allowlists; the validator also fixes their owner, type,
TTL, and answer values. Allowlisting one record never authorizes another, stale keys and
wildcards fail closed, and `mindclade.com` has no public-address exception. Public address
answers were also observed for `mindclade.studio`, but they remain absent from desired source and
carry a separate reconciliation blocker because the target private-only service plane conflicts
with them. These observations are not zone exports and do not make any incumbent inventory
complete.

The v0.4.0 candidate live units use the typed `dns_name` interface and explicit record `name`
overrides, so multiple record types can safely share an owner such as the apex. Its
`public_record_allowlist` accepts only exact records-map keys for reviewed public `A`, `AAAA`, or
`CNAME` exceptions; all other public address records remain denied. This is source compatibility
only: `release_status` remains `planned`, every domain carries the
`dns-module-ref-not-published` blocker, and the incumbent inventories are incomplete. The DNS
module itself enforces both provider deletion prevention and Terraform `prevent_destroy`; do not
add a live `deletion_protection` field because it is not part of the typed module input.
Do not point a live unit at a branch or delegate an empty or partially inventoried zone.
The normalized contract also keeps the migration window `unapproved`; approving it requires a
change reference and bounded, timezone-aware start/end timestamps before any domain blocker may
be cleared.

## Automated controls

Static validation runs locally and in pull-request CI:

```sh
python3 scripts/validate_dns_portfolio.py
python3 scripts/validate_dns_portfolio.py --require-ready mindclade.dev
```

The first command validates roles, ownership, DNSSEC, record types, exact public-address
allowlists and values, no-mail controls, module release status, shared DNS module interfaces,
and parity between the normalized inventory and live Terragrunt records. The second additionally
fails unless the selected domain is explicitly ready. Qualify in the fixed order
`mindclade.dev` → `mindclade.ai` → `mindclade.studio` → `mindclade.com`; never parallelize
registrar delegation.

The manually dispatched **DNS cutover check** workflow is read-only. Its `preflight` phase
compares every reviewed portable record on the incumbent and Cloud DNS nameservers. After the
old DS is removed, `predeligation` requires parent DS absence, target SOA and DNSKEY presence,
and complete Cloud DNS snapshot agreement on every target nameserver. `postcutover` checks
public delegation and the complete snapshot, with an optional DS/DNSKEY presence gate after
DNSSEC is re-established. It uploads timestamped JSON evidence and uses only the protected
read-only plan identity to snapshot Cloud DNS; it has no registrar or cloud mutation path. A
nightly monitor repeats public NS, SOA, DS, DNSKEY, MX, SPF, DMARC, CAA, generated-CNAME, and
authoritative-server agreement checks for every delegation-ready domain. Follow the
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
