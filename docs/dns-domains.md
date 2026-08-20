# Mindclade domain portfolio and DNS ownership

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

Before changing Squarespace nameservers, import all existing records, lower TTLs, query the
new authoritative nameservers directly, disable the old DNSSEC chain, change delegation,
verify web and email, then publish the Cloud DNS DS record at Squarespace.
