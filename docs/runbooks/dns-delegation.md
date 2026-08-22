<!-- mindclade-doc: runbook@1 -->

# Cloud DNS delegation cutover and rollback

> **Scope:** `mindclade.com`, `mindclade.ai`, `mindclade.dev`, and `mindclade.studio`<br>
> **Authority:** Cloud DNS records are applied from `infrastructure-live`; Squarespace remains
> the registrar and is changed only by an approved operator.

## Safety contract

The workflow named **DNS cutover check** is read-only. It queries DNS, uses the protected plan
identity to snapshot record sets from Cloud DNS, and uploads evidence; it has no Squarespace
credential, registrar write path, or cloud mutation permission. Nameserver and DS changes remain
manual because a bad automated delegation can make the whole domain unreachable before the
automation can repair itself.

Do not delegate a domain unless all of these are true:

- `contracts/dns-domain-inventory.json` marks its inventory complete and
  delegation-ready with no activation blockers.
- The inventory marks the DNS module ref `published`, and the exact immutable-ref interface
  gate passes against the protected monorepo checkout.
- The approved migration window has a change reference and bounded start/end timestamps.
- Certificate Manager DNS authorizations, issuer inventory, and CAA policy are ready for every
  certificate-serving domain; public and private endpoint names match the environment contract.
- `python3 scripts/validate_dns_portfolio.py --require-ready <domain>` passes.
- The protected Cloud DNS plan and apply completed for the exact reviewed commit.
- A preflight evidence run passes against every incumbent and Cloud DNS nameserver.
- The incumbent zone remains unchanged through the rollback window.
- The change record contains old and new nameservers, old and new DS data, TTLs, timestamps,
  operators, and the rollback deadline.

The planned DNS module interface permits public `TXT`, `CAA`, `MX`, and delegated-child `NS`
records by default. Public `A`, `AAAA`, or `CNAME` records require an exact reviewed records-map
key in `public_record_allowlist`; the inventory validator also pins the approved owner, type,
TTL, and answer values. The only current exceptions are `apex-a` and `www-cname` for
`mindclade.ai` and `mindclade.dev`. Wildcards, stale allowlist entries, and any additional public
address record fail closed. Deployment additionally requires the protected module release tag
and exact-ref validation. If an incumbent inventory needs any different public address record,
stop and reconcile the public-service architecture through a separate module-and-inventory
review rather than omitting the record or weakening validation.

## Symptoms and impact

| Symptom | Likely failure | Impact |
| --- | --- | --- |
| `SERVFAIL` for the apex | stale or incorrect DS chain | the entire domain may be unreachable |
| Cloud nameservers disagree | incomplete apply or record drift | intermittent resolution by resolver |
| Public NS remains at Squarespace | registrar propagation incomplete | clients still use the incumbent zone |
| Website or identity hostname fails | record omitted from reviewed inventory | service-specific outage |
| Gmail cannot receive mail | MX missing or different from the incumbent zone | inbound mail delayed or bounced |
| Gmail authentication fails | SPF, DKIM, or DMARC mismatch | outbound mail rejected or sent to spam |

## Read-only diagnosis

Validate source state first:

```sh
python3 scripts/validate_dns_portfolio.py --require-ready mindclade.dev
```

Run the manual **DNS cutover check** workflow from `main` with:

- `phase`: `preflight`
- `incumbent_nameservers`: every current authoritative nameserver
- `cloud_nameservers`: every nameserver from the Cloud DNS zone output
- `expect_dnssec`: false
- `change_reference`: the approved `CHG-`, `INC-`, `SEC-`, or `DR-` identifier

The workflow compares SOA availability and every inventoried record set on every named server.
Keep its JSON artifact with the change record.

After the incumbent DS has been removed and its cache interval has elapsed, run the workflow
again with `phase=predeligation`. This phase reads the complete target zone snapshot and refuses
cutover unless every parent nameserver reports the DS absent, every target nameserver serves SOA
and DNSKEY, and every target answer agrees with the snapshot. Do not substitute a recursive
resolver's empty DS answer for the direct parent-authoritative checks.

For local diagnosis from the pinned development shell:

```sh
nix develop
python3 scripts/check_dns_delegation.py \
  --domain mindclade.dev \
  --phase preflight \
  --incumbent-nameservers '<old-ns-1>,<old-ns-2>' \
  --cloud-nameservers '<cloud-ns-1>,<cloud-ns-2>,<cloud-ns-3>,<cloud-ns-4>' \
  --change-reference CHG-0000 \
  --output /tmp/mindclade-dev-dns-preflight.json
```

## Resolution and cutover

Perform one domain at a time in this fixed order: `mindclade.dev`, `mindclade.ai`,
`mindclade.studio`, then `mindclade.com`. The first three prove the no-mail path before the
mail-enabled corporate domain is exposed to change.

1. Confirm the preflight evidence status is `PASS`.
2. At Squarespace, remove or disable the incumbent DNSSEC/DS chain. Wait the approved interval
   derived from the current DS and DNSKEY TTLs before changing nameservers.
3. Run **DNS cutover check** with `phase=predeligation` and retain its passing evidence. Do not
   continue if any parent nameserver still publishes DS or any target nameserver disagrees.
4. Replace the Squarespace nameservers with the complete Cloud DNS nameserver set. Do not
   delete the incumbent zone.
5. Run **DNS cutover check** with `phase=postcutover` and `expect_dnssec=false` until public
   delegation and every inventoried answer pass.
6. Verify affected web and identity endpoints. For `mindclade.com`, verify real inbound and
   outbound Workspace mail plus SPF and DKIM authentication; DNS queries alone do not prove
   message delivery.
7. Publish the Cloud DNS DS data at Squarespace.
8. Run the post-cutover check again with `expect_dnssec=true`. This confirms public DS and
   authoritative DNSKEY presence; retain an independent validating-resolver result with the
   change evidence.
9. Keep the incumbent zone unchanged until the rollback deadline passes.

## Rollback

If critical answers fail before the new DS is published:

1. Restore the previous Squarespace nameserver set.
2. Restore the previous DS state only when it matches the restored authoritative zone.
3. Query each restored nameserver directly and then verify public delegation.

If the new Cloud DNS DS was already published:

1. Remove the new DS at Squarespace first.
2. Wait the approved DS cache interval and verify the parent no longer publishes it.
3. Restore the incumbent nameservers.
4. Restore the incumbent DS only after the incumbent authoritative DNSKEY is visible again.

Never point delegation at an unsigned or differently signed zone while an incompatible DS is
published. That creates a DNSSEC-bogus response and validating resolvers return `SERVFAIL`.

## Escalation

Escalate to Infrastructure and Security when any nameserver disagrees, a DS/DNSKEY chain is
uncertain, an expected record is absent, or rollback evidence is incomplete. Escalate
`mindclade.com` mail failures to the Workspace administrator as well. Do not weaken DNSSEC,
mail authentication, or the public-record policy to make a check pass.

## Prevention

- Keep record changes in the normalized inventory and Terragrunt unit in the same pull request.
- Keep all domains blocked until their incumbent inventory is independently reviewed.
- Retain the nightly Terraform drift workflow and DNS evidence artifacts.
- Keep the nightly DNS portfolio monitor green; it reconciles one drift issue per ready domain.
- Drill rollback on a non-mail domain before migrating `mindclade.com`.
