<!-- mindclade-doc: how-to@1 -->

# Hand an environment to GitOps

> **Audience:** platform operators activating a new or reconstructed GKE environment.
> **Outcome:** transfer control from provisioned cloud infrastructure to the pinned GitOps root
> without creating overlapping ownership.
> **Risk:** critical—an incorrect handoff can create overlapping owners or reconcile the wrong cluster.

Terraform does not install Argo CD or apply workload manifests. `infrastructure-live` creates the
cloud prerequisites; the `gitops` repository performs the one-time Argo CD bootstrap, after which
Argo CD self-manages from Git.

## Ownership boundary

| `infrastructure-live` owns | `gitops` owns |
|---|---|
| Cluster, node pools, private network, and workload identity | Argo CD installation and root Application |
| Registry, Secret Manager containers, and KMS resources | In-cluster policies, operators, namespaces, and workloads |
| Binary Authorization policy and attestor prerequisites | Digest-pinned workload references and deployment intent |
| Storage, databases, backup, and cloud observability | Kubernetes reconciliation and application health |

## Before handoff

1. Apply every required Terragrunt unit through the protected workflow using the reviewed saved
   plan.
2. Confirm the cluster endpoint and authorized access path work from the bootstrap runner.
3. Confirm GitOps service identities can read required repositories, secrets, and artifacts while
   denied unrelated resources.
4. Confirm Binary Authorization, policy, DNS, certificate, storage, database, backup, and
   observability prerequisites for the selected environment are ready.
5. Record the infrastructure commit, GitOps commit, cluster identity, environment, operator, and
   rollback owner in the change record.

Do not proceed while any prerequisite is represented only by a planned resource or mock output.

## Activate reconciliation

1. Check out the reviewed GitOps commit and use its pinned toolchain.
2. Run the repository validation contract.
3. Run the GitOps bootstrap script for the selected environment and profile exactly as documented
   in that repository.
4. Allow the root Application to create the environment ApplicationSet and child Applications.
5. Do not manually create workload resources or force-sync around a failed gate.

## Verify the handoff

- Argo CD reports the root and generated Applications as healthy and synchronized.
- The running Argo CD version/profile matches the pinned GitOps source.
- Required policies and operators reconcile before workloads.
- Workloads use immutable qualified digests and pass Binary Authorization.
- Cloud and in-cluster observability receive expected health signals.
- A no-change infrastructure plan does not propose GitOps-owned Kubernetes resources.

If reconciliation fails, preserve the exact commits and events and follow the GitOps
[`failed-sync.md`](https://github.com/mindclade/gitops/blob/main/docs/failed-sync.md) runbook. If
cloud prerequisites are missing, repair them through a reviewed infrastructure plan before
retrying the handoff.

## Roll back or recover

Before the root Application is active, stop and correct the prerequisite or bootstrap input. After
GitOps owns the environment, do not remove Argo-managed resources with Terraform. Recover Argo from
the pinned GitOps commit or reconstruct the cluster with
[GKE reconstruction](runbooks/gke-reconstruction.md), depending on the failure boundary.
