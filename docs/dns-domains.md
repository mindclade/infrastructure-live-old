<!-- mindclade-doc: reference@1 -->

# Mindclade domain portfolio and DNS ownership

> **Audience:** DNS, platform, and security operators.
> **Outcome:** change domain delegation without losing web, identity, or mail service.

Squarespace remains the registrar. Google Cloud DNS is the authoritative DNS provider after
a controlled per-domain delegation.

| Domain | Role | Mail policy |
|---|---|---|
| `mindclade.com` | company, identity, email, trust | mail-enabled; import existing MX/SPF/DKIM/DMARC before delegation |
| `mindclade.ai` | production product, API, console, authentication; approved Squarespace apex and `www` exception | no-mail |
| `mindclade.dev` | developer documentation, SDKs, schemas; approved Squarespace apex and `www` exception | no-mail |
| `mindclade.studio` | demos, playgrounds, isolated experiments; public Squarespace site to retire | no-mail |

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
marks all four domains as blocked pending review. On 2026-08-21 the owning Cloudflare account
was recovered through `robpearc@mindclade.com`. The complete authoritative `mindclade.com` BIND
export has SHA-256 `c0c54f51f6d4ba853e140dac5e10009294c3424ee54c4b395d2fdfbd185925ca`.
It contains five Google MX records, Google verification TXT, the 2048-bit Workspace DKIM TXT,
and a proxied `_domainconnect` CNAME to Squarespace. Workers Routes, legacy Page Rules, custom,
rate-limit, and managed WAF rules, Email Routing destinations, Load Balancing, and Bulk
Redirects were empty or disabled. The raw export remains outside the repository as restricted
change evidence.

The committed `mindclade.com` record map in
[`3-networks/shared/public-zones/mindclade-com/terragrunt.hcl`](../3-networks/shared/public-zones/mindclade-com/terragrunt.hcl)
preserves the legacy Google MX set, Google verification TXT record, and 2048-bit
`google._domainkey` DKIM value observed through a read-only Admin-console and public-DNS
inventory on 2026-08-21. It also declares the reviewed final Google-only hard-fail SPF and
DMARC reject targets. Cloudflare remains authoritative through `cleo.ns.cloudflare.com` and
`rosa.ns.cloudflare.com`; the public zone did not serve those SPF or DMARC targets during the
read-only observation. Their presence in desired source is not connected evidence, so the
inventory remains incomplete and explicitly blocked on mail-authentication observation, sender
review, independent export review, and disposition of the proxied `_domainconnect` record.
Cloud DNS cannot preserve its proxy semantics, so desired source omits it until a reviewer
approves either a DNS-only exception or retirement. **Do not change registrar nameservers or
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
with them. A historical, non-authoritative Cloudflare `.studio` export was also preserved with
SHA-256 `56a21b9de85df38466f333f0c1814ddcfcd5e0b67a8c0add8677d205d4d4b38d`.
It is stale and lacks the Google MX and verification records currently served by Squarespace;
it is evidence only. Retire `.studio` public A, CNAME, and HTTPS records only after required
content is captured and redirect or application dependencies are disproved.

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

## Mail enforcement sequence

Before no-mail DNS is applied, audit Workspace users, aliases, groups, routing, and send-as
identities under `@mindclade.ai`, `@mindclade.dev`, and `@mindclade.studio`. Move every legitimate
identity to `mindclade.com`; any remaining secondary-domain sender or recipient blocks migration.
The final no-mail record sets are null MX `0 .`, SPF `v=spf1 -all`, and DMARC
`p=reject; sp=reject; adkim=s; aspf=s`. Each apex TXT record set also retains its exact Google
verification value.

Treat Google Workspace as the only authorized `mindclade.com` sender unless the sender audit
proves otherwise. First publish incumbent SPF `v=spf1 include:_spf.google.com ~all` and DMARC
`p=none; sp=none; pct=100; adkim=s; aspf=s` with aggregate reports to
`security@mindclade.com`. Observe real reports for 14 days. Only after every legitimate sender is
accounted for may incumbent and target advance to SPF `-all` and DMARC `p=reject; sp=reject`.
The strict target values in desired source do not authorize skipping this observation period.

## Automated controls

Static validation runs locally and in pull-request CI:

```sh
nix develop .#ci --command make validate-dns
nix develop .#ci --command python3 scripts/validate_dns_portfolio.py --require-ready mindclade.dev
```

The first command checks the generated projection, executes the committed Draft 2020-12 schema,
runs the DNS-focused tests, and validates roles, ownership, DNSSEC, record types, exact
public-address allowlists and values, exact reviewed Google verification and Workspace MX/DKIM
records, strict no-mail alignment, module release status, shared DNS module interfaces, evidence
governance, and parity between the normalized inventory and live Terragrunt records. The second
additionally fails unless the selected domain is explicitly ready. Qualify in the fixed order
`mindclade.dev` → `mindclade.ai` → `mindclade.studio` → `mindclade.com`; never parallelize
registrar delegation.

Independent reviewed comparison pins for verification and Workspace MX, plus the hash-only
Workspace DKIM pin, live in the versioned
[`dns-reviewed-record-pins.json`](../contracts/dns-reviewed-record-pins.json) contract governed by
its adjacent Draft 2020-12 schema. `DNS-PINS-*` diagnostics cover loading, schema, and
record-match failures for that contract and intentionally omit expected and observed RRdata and
hashes; broader inventory diagnostics retain their existing messages.

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
2. Normalize only reviewed portable records. Preserve mail TTLs and semantics; do not synthesize
   missing values or silently convert a proxied Cloudflare record to DNS-only behavior.
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

## Google Workspace read-only audit (2026-08-22)

A read-only Google Admin and Gmail audit completed at `2026-08-22T03:55:41Z` confirmed that `mindclade.com`, `mindclade.ai`, `mindclade.dev`, and `mindclade.studio` are verified and currently report Gmail activated. The tenant has one active user, `robpearc@mindclade.com`, with no populated alternate addresses. Its eight groups all use `mindclade.com` and expose no aliases under the three no-mail domains.

No Workspace host, default-routing rule, outbound gateway, non-Gmail route, SMTP relay, recipient map, inbound gateway, compliance route, spam route, mailbox forward, Gmail filter, delegate, external SMTP send-as identity, or secondary-domain send-as identity was found. Organization policy allows automatic forwarding, but the sole mailbox has no configured forwarding address; mail delegation and per-user outbound gateways are off.

All four `google._domainkey` public selectors currently resolve and Google Admin reports DKIM authentication started for each domain. Removing the `.ai`, `.dev`, and `.studio` selectors from their target no-mail zones is therefore an intentional retirement that must be named in each change record, not treated as an inventory omission.

The redacted report was captured as restricted change evidence with SHA-256
`6c7ff043b247814e6d26ba27ae22ebb009f19156403e7b9a8c6991c72c1d0376`. Canonical readiness
remains blocked until an independent reviewer accepts that evidence and all remaining DNS,
certificate, site-retirement, release, project, and cutover gates are complete. No Google Admin
or DNS mutation was performed during the audit.
