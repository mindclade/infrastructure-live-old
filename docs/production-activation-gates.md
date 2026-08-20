<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

# Production activation gates

The live tree is a production target, but static configuration is not proof that quota,
provider behavior, private module interfaces, or recovery paths work in Mindclade's Google
Cloud organization. A gate marked **Unknown** or **Proposed** blocks the affected production
capability; it is not an invitation to infer a safe default.

| Capability | Repository evidence | Status before a production apply |
|---|---|---|
| Private module interfaces | Every remote module is immutable-pinned and CI has a read-only interface preflight | **Unknown:** run preflight against the exact monorepo refs, then a credentialed saved plan |
| Organization-policy baseline | `1-org/org-policies` is the sole owner for key prohibition, domain-restricted sharing, uniform bucket access, public-access prevention, external-IP, contact-domain, and workload constraints; its local v2 implementation represents parameterized managed constraints without legacy aliases | **Unknown:** retain cataloged `baseline` phase while importing Google's seven auto-provisioned policies and proving a zero-change saved plan; switch to `extended` only in a later reviewed change after Policy Simulator/dry-run and lockout recovery qualify every additional constraint |
| Essential Contacts | `1-org/essential-contacts` declares governed organization and folder group routes | **Unknown:** confirm each group exists, test every subscription route, and verify the allowed-domain policy before depending on notifications |
| KMS ownership | Normal and Binary Authorization keys currently reference the bootstrap seed project | **Proposed migration:** move normal KMS authority to an infrastructure-owned common security project with state moves and decrypt/sign verification; never recreate a key in place |
| VPC Service Controls | Staging and production are dry-run; development is configured to enforce | **Unknown:** retain dry-run until denial logs, CI/developer paths, ingress/egress tests, and the denial runbook have been qualified |
| DR geography and encryption | Backup units currently use the primary region and the production SQL replica has a different-region/no-key contract | **Proposed:** approve a secondary region, create matching regional KMS keys, validate residency, and complete restore drills before claiming regional DR |
| Workload identities and holdout data | Holdout policy names training/preprocessing identities that are not created in this tree | **Unknown:** bind real GKE workload principals, prove training denial and evaluation-only access, and remove placeholder principals |
| Supply-chain signer | Buildkite build, Buildkite qualification, and GitHub deployment attestors have separate named issuers; global production admission requires deployment trust | **Unknown:** qualify exact note/key IAM, module outputs, GitHub signer WIF, and cross-identity negative tests before publishing variables |
| GPU capacity | A3/A4 pools are zonal, tainted, bounded, and scale to zero | **Unknown:** obtain quota/capacity evidence and reservations for critical serving; a configured pool is not capacity assurance |
| Production paging | Metrics and alert policies are declared | **Unknown:** connect production alerts to a staffed paging route and exercise notification delivery |
| Initial apply ordering | Terragrunt dependencies model resource dataflow | **Proposed:** apply clean-room layers in documented order; do not assume a multi-scope workflow matrix establishes first-build sequencing |

## Argo CD high-availability gate

**Current disposition: standard profile.** The production GKE control plane is regional, but
the live inputs do not prove at least three schedulable system nodes across three zones. The
default pool has a minimum of one; the untainted CPU pool has a minimum of two and does not
declare `node_locations`. Private module behavior and the resulting plan are unavailable in
this checkout.

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
