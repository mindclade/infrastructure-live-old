<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

# Production activation gates

The live tree is a production target, but static configuration is not proof that quota,
provider behavior, private module interfaces, or recovery paths work in Mindclade's Google
Cloud organization. A gate marked **Unknown** or **Proposed** blocks the affected production
capability; it is not an invitation to infer a safe default.

| Capability | Repository evidence | Status before a production apply |
|---|---|---|
| Private module interfaces | Candidate source validation checks declared and required variables for the planned v0.4.0 worktree while preserving exact Git-tree validation for every released tag/SHA | **Blocked on release provenance:** planned-source validation passes all 106 live units, but the exact-ref gate intentionally rejects the unpublished v0.4.0 tag. No affected scope may plan or apply until a protected tag is published from the reviewed commit, exact validation passes, and a credentialed saved plan is retained |
| Organization-policy baseline | `1-org/org-policies` is the sole owner for key prohibition, domain-restricted sharing, uniform bucket access, public-access prevention, external-IP, contact-domain, and workload constraints; its local v2 implementation represents parameterized managed constraints without legacy aliases | **Unknown:** retain cataloged `baseline` phase while importing Google's seven auto-provisioned policies and proving a zero-change saved plan; switch to `extended` only in a later reviewed change after Policy Simulator/dry-run and lockout recovery qualify every additional constraint |
| Essential Contacts | `1-org/essential-contacts` declares governed organization and folder group routes | **Unknown:** confirm each group exists, test every subscription route, and verify the allowed-domain policy before depending on notifications |
| KMS ownership | Normal and Binary Authorization keys currently reference the bootstrap seed project | **Proposed migration:** move normal KMS authority to an infrastructure-owned common security project with state moves and decrypt/sign verification; never recreate a key in place |
| VPC Service Controls | Staging and production are dry-run; development is configured to enforce | **Unknown:** retain dry-run until denial logs, CI/developer paths, ingress/egress tests, and the denial runbook have been qualified |
| DR geography and encryption | Backup units currently use the primary region and the production SQL replica has a different-region/no-key contract | **Proposed:** approve a secondary region, create matching regional KMS keys, validate residency, and complete restore drills before claiming regional DR |
| Workload identities and holdout data | Dedicated keyless system/GPU node identities now exist; holdout policy still names training/preprocessing identities that are not created in this tree | **Unknown:** bind real GKE workload principals, prove training denial and evaluation-only access, and remove placeholder principals |
| Supply-chain signer | ARC build, ARC qualification, and protected GitHub deployment attestors use separate capability identities; global production admission requires deployment trust | **Unknown:** qualify exact note/key IAM, applied identity outputs, all six WIF paths, and cross-identity negative tests before publishing variables |
| GPU capacity | Terraform is the sole capacity authority for zonal H100 A3 Mega and B200 A4 High pools; labels and taints match held Kueue flavors and both pools scale to zero | **Unknown:** qualify current regional support, reservations or queued capacity, quota, driver/fabric/topology, checkpoint/restart, and cost before raising Kubernetes and Kueue quotas |
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
