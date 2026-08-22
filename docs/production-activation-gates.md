<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

# Production activation gates

The live tree is a production target, but static configuration is not proof that quota,
provider behavior, private module interfaces, or recovery paths work in Mindclade's Google
Cloud organization. A gate marked **Unknown** or **Proposed** blocks the affected production
capability; it is not an invitation to infer a safe default.

| Capability | Repository evidence | Status before a production apply |
|---|---|---|
| Private module interfaces | Candidate source validation checks declared and required variables for the planned v0.4.0 worktree while preserving exact Git-tree validation for every released tag/SHA | **Blocked on release provenance:** planned-source validation passes the live module callers, but the exact-ref gate intentionally rejects the unpublished v0.4.0 tag. No affected scope may plan or apply until a protected tag is published from the reviewed commit, exact validation passes, and a credentialed saved plan is retained |
| U.S. residency | `RESIDENCY_PROFILE=us-only-v1` fixes the primary region/zone to `us-central1`/`us-central1-b`, recovery to `us-east4`/`us-east4-b`, state to `US`, and organization policy to `in:us-locations`; source validation rejects deployable non-U.S. region literals | **Source complete, activation blocked:** retain exact variables and review Policy Simulator output plus credentialed plans before applying the location constraint or any regional resource |
| Organization-policy baseline | `1-org/org-policies` is the sole owner for key prohibition, domain-restricted sharing, uniform bucket access, public-access prevention, external-IP, contact-domain, and workload constraints; its local v2 implementation represents parameterized managed constraints without legacy aliases | **Unknown:** retain cataloged `baseline` phase while importing Google's seven auto-provisioned policies and proving a zero-change saved plan; switch to `extended` only in a later reviewed change after Policy Simulator/dry-run and lockout recovery qualify every additional constraint |
| Essential Contacts | `1-org/essential-contacts` declares governed organization and folder group routes | **Unknown:** confirm each group exists, test every subscription route, and verify the allowed-domain policy before depending on notifications |
| KMS ownership | Normal and Binary Authorization keys currently reference the bootstrap seed project | **Proposed migration:** move normal KMS authority to an infrastructure-owned common security project with state moves and decrypt/sign verification; never recreate a key in place |
| VPC Service Controls | Staging and production are dry-run; development is configured to enforce | **Unknown:** retain dry-run until denial logs, CI/developer paths, ingress/egress tests, and the denial runbook have been qualified |
| DR geography and encryption | Every environment declares independent `us-east4` HSM keys, an immutable recovery registry, region-local Backup for GKE CMEK, hourly raw/checkpoint replication, two-region Secret Manager replicas, and a CMEK-protected Cloud SQL recovery replica; production GKE backups are hourly | **Source complete, activation blocked:** prove supported service locations, key/service-agent access, image parity, replication lag, point-in-time recovery, regional restore, and DNS/failover behavior through connected drills before claiming regional DR |
| DR drill evidence | `bootstrap/contracts/drill-matrix.json` fixes ten scratch/staging objectives, RPO/RTO, cadence, two distinct operators, protected review, report v2, and append-only v5 evidence publication | **Not run:** source validation is green, but no actual measured report is present. Execute each due drill with the primary/observer protocol, archive the report and access-log proof, and close corrective actions before qualifying recovery |
| Bazel remote execution | v0.4.0 candidate modules create a protected cache, dedicated keyless GKE identity and multi-zone CPU pool; the monorepo pins Buildfarm 2.17.0 AMD64/ARM64 images, exports Nix action bases, renders zero-replica Kubernetes source, and compares local/remote output digests | **Source complete, activation blocked:** publish v0.4.0 and v5.0.0, retain native Nix rebuild/image attestations, mirror exact Buildfarm indexes, provide private HA Redis and TLS, then prove executed-action parity, cache failure modes, drain, failover, SLO, and rollback before any client endpoint is configured |
| Public DNS portfolio | The canonical JSON inventory generates the human projection and all four protected public-zone inputs; separate environment-private service zones consume exact Gateway VIPs; regional Certificate Manager units create one per-project authorization CNAME per exact SAN; Gateway/route consumers use explicit environment-qualified names; cutover automation requires parent DS absence and full target agreement; nightly monitoring reconciles external drift issues | **Source complete, activation blocked:** v0.4.0 is unpublished; incumbent exports/review and a migration window are absent; Certificate Manager resources are unapplied and issuer/CAA approval is incomplete; and the incumbent public `mindclade.studio` address still conflicts with the private-only target. Qualify one domain at a time in `mindclade.dev` → `mindclade.ai` → `mindclade.studio` → `mindclade.com` order, with real Workspace mail data imported and tested before the corporate domain |
| Workload identities and holdout data | Each environment creates separate, keyless preprocessing, H100-training, B200-training, and holdout-evaluator GSAs with zero project-wide roles; exact KSA bindings are cross-checked against environment overlays, the holdout deny consumes the three training service-account outputs, and the evaluator receives one additive bucket-scoped object-viewer grant | **Blocked on release and connected evidence:** publish the reviewed v0.4.0 module ref, retain credentialed plans, prove each KSA can impersonate only its selected GSA, prove all three training identities are denied holdout reads, and qualify the dedicated evaluation-only reader using the [qualification runbook](runbooks/workload-identity-holdout-qualification.md) before activating evaluation |
| Supply-chain signer | ARC build, ARC qualification, and protected GitHub deployment attestors use separate capability identities; global production admission requires deployment trust | **Unknown:** qualify exact note/key IAM, applied identity outputs, all six WIF paths, and cross-identity negative tests before publishing variables |
| GPU capacity | Terraform is the sole capacity authority for zonal H100 A3 Mega and B200 A4 High pools; each expensive pool scales from zero and is bounded to one eight-GPU node, while topology-aware Kueue flavors, quotas, and qualification jobs remain held | **Unknown:** qualify current regional support, reservations or queued capacity, quota, driver/fabric/topology, checkpoint/restart, and cost before raising Kubernetes and Kueue quotas |
| Production paging | The reusable SLO/burn-alert module exists, but the legacy live unit does not match it and runtime good/total request metrics plus tested channel resource names are not yet available | **Blocked:** implement bounded runtime metrics and pre-existing staffed channel resources, then apply the exact module contract and exercise open/recovery delivery |
| Initial apply ordering | Terragrunt dependencies model resource dataflow | **Proposed:** apply clean-room layers in documented order; do not assume a multi-scope workflow matrix establishes first-build sequencing |

## Argo CD high-availability gate

**Current disposition: standard profile.** The production source target now uses the hardened
regional GKE module with a protected three-node minimum system pool and an on-demand CPU pool
declaring three zones. Static source is not evidence of actual zone distribution, quota,
autoscaler behavior, or failure tolerance, and the resulting credentialed plan is unavailable
in this checkout.

Changing GitOps production to the HA profile requires all of the following evidence:

1. The node-pool module exposes and the production unit declares exactly three approved
   `node_locations` in the production region.
2. Autoscaling semantics guarantee a total minimum of at least three schedulable,
   non-Spot system nodes, with at least one node in each selected zone.
3. Argo CD components have qualified PodDisruptionBudgets and topology-spread or
   anti-affinity rules that use those zones.
4. A staging failure-domain exercise proves reconciliation continues after losing one zone.
5. The credentialed production plan shows the intended node distribution and no destructive
   cluster replacement.

Until every item is recorded, GitOps and bootstrap documentation must select the standard
profile and must not describe production Argo CD as HA.

## Evidence record

For each gate, retain the exact source SHA, module refs, plan checksum, reviewers, test or
drill output, owner, and expiration/revalidation date. Evidence belongs in the approved
change or incident system; raw state and raw plan contents do not belong in Git.
