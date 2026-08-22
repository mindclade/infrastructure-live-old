<!-- mindclade-doc: runbook@nix-binary-cache-activation@1 -->

# Nix binary-cache qualification and activation

<<<<<<< HEAD
> **Platform Foundation · Protected cache publication**  
=======
> **Platform Foundation · Protected cache publication**
>>>>>>> origin/codex/nix-cache-infra-20260822
> Qualify a private Attic service without granting pull requests write authority or exposing
> server signing material to any client.

## Safety boundary

`contracts/nix-binary-cache.json` is the machine-readable authority. Its lifecycle is monotonic:

| State | Server | Protected publication | Nix client substituter |
| --- | --- | --- | --- |
| `proposed` | Zero replicas, invalid endpoint | Disabled | Disabled |
| `qualifying` | Private HA endpoint under connected test | Enabled only through the protected environment | Disabled |
| `qualified` | Private HA endpoint with retained evidence | Enabled only through the protected environment | Disabled |
| `activated` | Same qualified service | Enabled | Enabled with the reviewed public key and private read authentication |

Never skip `qualifying` or `qualified`. A raw private GCS bucket is backend storage, not a Nix substituter.
Neither Terraform state, GitHub Actions, pull-request jobs, nor client configuration may contain
the Attic token-signing private key or the GCS HMAC secret. Terraform creates only secret
containers. An authorized operator generates HMAC material out of band and writes secret
versions through a protected, audited process.

## Proposed-state validation

Run the credential-free source checks before any plan:

```sh
python3 scripts/validate_nix_binary_cache.py
python3 scripts/validate_nix_binary_cache.py --monorepo ../mindclade-internal-monorepo
```

Expected output names the `proposed` lifecycle. `--require-active` must fail. The checked-in
Kubernetes source remains at zero replicas with an `.invalid` endpoint, default-deny networking,
disabled automatic garbage collection, and no active GitOps target. The reusable publication
workflow has no caller while this state remains proposed.

## Qualification prerequisites

Protected reviewers must retain all of the following before changing the lifecycle:

1. Immutable module `v0.4.0` and shared-workflow contract `v5.0.0` resolve to their reviewed
   source commits; neither tag is created or moved from an agent session.
2. Credentialed saved plans cover the storage, KMS, identity, and secret-container units, and
   retained applied evidence matches those plans.
3. The exact Attic image is mirrored, scanned, attested, and accepted despite its upstream
   early-prototype maturity label. The separately pinned client and server commits pass connected
   API, upload, retry, and recovery compatibility tests.
4. A private, TLS-authenticated endpoint, HA PostgreSQL service, backups, and restore drill exist.
5. GCS XML API HMAC issuance and rotation keep the secret out of source, logs, plan artifacts,
   Terraform state, and GitHub.
6. Multipart uploads, retries, duplicate writes, proof of possession, token scope, negative
   authentication, and create-only object semantics pass connected tests.
7. Server signing-key and token recovery, signature-tamper rejection, cold/warm builds, complete
   cache loss, growth limits, alerts, and cost ownership have retained evidence.
8. The current `nixos-unstable` input and platform list remain unchanged. `x86_64-darwin` stays
   explicitly unsupported; restoring it or changing release lines requires a separate change
   with native Darwin proof.
9. The protected GitHub environment is observed live with its exact repository assignment before
   a separately reviewed caller is added for `qualifying`.

The evidence record must identify the protected plan artifact, change record, reviewer,
<<<<<<< HEAD
timestamp, immutable object generation, and SHA-256 without embedding credentials.
=======
timestamp, immutable object generation, SHA-256, and evidence-ledger verification digest without
embedding credentials. Store it below the contract's exact prefix in the locked production
qualification archive.
>>>>>>> origin/codex/nix-cache-infra-20260822

## Qualify

An authorized operator may apply only the reviewed saved plans, create secret values outside
Terraform, and activate the GitOps operator overlay. Keep every Nix client disabled. After the
endpoint, replicas, trusted public key, module release, and protected publisher exist, advance
only to `qualifying`, retaining every unresolved blocker. Use the protected
`nix-cache-publication` environment to populate the four Linux CI shells and all
`packages.x86_64-linux` outputs. Pull requests and merge-queue candidates receive neither a write
token nor signing material.

Run backend retry, concurrency, duplicate-write, corruption, authentication, restore, rotation,
and cache-loss exercises. Record every evidence boolean as true, clear the blocker list, publish
the exact HTTPS endpoint and trusted public key, set server replicas to at least two, and advance
the contract only to `qualified`. Validation must remain green while `client.enabled` is false.

## Activate

After an independent review of qualification evidence, enable private authenticated reads in one
trusted canary lane. Verify signature rejection for an untrusted key and verify that a missing or
unreachable cache falls back to a successful local build. Then expand to protected main and
merge-group lanes before pull-request reads. Only after those observations may the contract move
to `activated` and this gate pass:

```sh
python3 scripts/validate_nix_binary_cache.py --require-active
```

Do not configure a global developer substituter automatically. Developers opt in only after the
same endpoint authentication and public key are distributed through an approved local mechanism.

## Rollback and recovery

At the first signature, authorization, availability, cost, or integrity failure:

1. Remove the substituter from every client before changing the server.
2. Disable the protected publisher and revoke its scoped token; do not rotate the signing key as
   a first response unless compromise is suspected.
3. Confirm local builds succeed without the cache and preserve endpoint, database, object,
   access-log, and alert evidence.
4. Scale the service down only after clients are detached. Never delete the bucket, database,
   key, or secret versions during containment.
5. Restore PostgreSQL and signing material into an isolated endpoint, prove signatures and object
   references, then repeat qualification. Rebuilding an empty cache is always safer than trusting
   unverifiable content.

Destructive cleanup requires a separate change record, retention expiry, saved plan, and explicit
approval. This runbook grants no cloud, GitHub, or secret authority.
