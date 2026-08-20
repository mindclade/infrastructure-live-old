<!-- mindclade-doc: runbook@1 -->

# Cloud DNS delegation cutover and rollback

> **Scope:** `mindclade.com`, `mindclade.ai`, `mindclade.dev`, and `mindclade.studio`<br>
> **Authority:** Cloud DNS records are applied from `infrastructure-live`; Squarespace remains
> the registrar and is changed only by an approved operator.

## Safety contract

The workflow named **DNS cutover check** is read-only. It queries DNS and uploads evidence; it
has no Google Cloud identity, Squarespace credential, or registrar write path. Nameserver and
DS changes remain manual because a bad automated delegation can make the whole domain
unreachable before the automation can repair itself.

Do not delegate a domain unless all of these are true:

- `contracts/dns-domain-inventory.json` marks its inventory complete and
  delegation-ready with no activation blockers.
- `python3 scripts/validate_dns_portfolio.py --require-ready <domain>` passes.
- The protected Cloud DNS plan and apply completed for the exact reviewed commit.
- A preflight evidence run passes against every incumbent and Cloud DNS nameserver.
- The incumbent zone remains unchanged through the rollback window.
- The change record contains old and new nameservers, old and new DS data, TTLs, timestamps,
  operators, and the rollback deadline.

The released DNS module permits public `TXT`, `CAA`, `MX`, and delegated-child `NS` records.
If the incumbent inventory contains public `A`, `AAAA`, or `CNAME` records, stop. Reconcile the
public-service architecture and release a reviewed module change rather than omitting those
records or bypassing the validation.

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
python3 scripts/validate_dns_portfolio.py --require-ready mindclade.studio
```

Run the manual **DNS cutover check** workflow from `main` with:

- `phase`: `preflight`
- `incumbent_nameservers`: every current authoritative nameserver
- `cloud_nameservers`: every nameserver from the Cloud DNS zone output
- `expect_dnssec`: false
- `change_reference`: the approved `CHG-`, `INC-`, `SEC-`, or `DR-` identifier

The workflow compares SOA availability and every inventoried record set on every named server.
Keep its JSON artifact with the change record.

For local diagnosis from the pinned development shell:

```sh
nix develop
python3 scripts/check_dns_delegation.py \
  --domain mindclade.studio \
  --phase preflight \
  --incumbent-nameservers '<old-ns-1>,<old-ns-2>' \
  --cloud-nameservers '<cloud-ns-1>,<cloud-ns-2>,<cloud-ns-3>,<cloud-ns-4>' \
  --change-reference CHG-0000 \
  --output /tmp/mindclade-studio-dns-preflight.json
```

## Resolution and cutover

Perform one domain at a time, starting with `mindclade.studio`; migrate `mindclade.com` last.

1. Confirm the preflight evidence status is `PASS`.
2. At Squarespace, remove or disable the incumbent DNSSEC/DS chain. Wait the approved interval
   derived from the current DS and DNSKEY TTLs before changing nameservers.
3. Replace the Squarespace nameservers with the complete Cloud DNS nameserver set. Do not
   delete the incumbent zone.
4. Run **DNS cutover check** with `phase=postcutover` and `expect_dnssec=false` until public
   delegation and every inventoried answer pass.
5. Verify affected web and identity endpoints. For `mindclade.com`, verify real inbound and
   outbound Workspace mail plus SPF and DKIM authentication; DNS queries alone do not prove
   message delivery.
6. Publish the Cloud DNS DS data at Squarespace.
7. Run the post-cutover check again with `expect_dnssec=true`. This confirms public DS and
   authoritative DNSKEY presence; retain an independent validating-resolver result with the
   change evidence.
8. Keep the incumbent zone unchanged until the rollback deadline passes.

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
- Drill rollback on a non-mail domain before migrating `mindclade.com`.
