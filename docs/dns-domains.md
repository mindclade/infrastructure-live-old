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

## Current activation gate

The committed `mindclade.com` record map in
[`3-networks/shared/public-zones/mindclade-com/terragrunt.hcl`](../3-networks/shared/public-zones/mindclade-com/terragrunt.hcl)
is currently empty. **Do not change registrar nameservers or DNSSEC delegation** until every
authoritative web, identity, mail, verification, and security record has been inventoried,
reviewed, and applied to Cloud DNS. An empty managed zone is not a delegation-ready zone.

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
