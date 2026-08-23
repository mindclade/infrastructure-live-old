# ARC cloud foundation

This tree creates the private regional GKE, network, registry, admission, cache, secret-container,
and dedicated node-pool prerequisites for GitHub ARC. It owns cloud resources, node identities,
networking, IAM, and bounded capacity. The `gitops` repository exclusively owns the ARC controller,
runner scale sets, namespaces, policies, secret references, and Argo CD desired state installed on
the cluster.

## Source and activation state

Every module-backed unit in this tree selects the planned `v0.4.0` module contract. That tag is
not release provenance until it is published from the reviewed monorepo commit, so source
validation can pass while plan/apply remains blocked. Before any mutation, publish the exact tag,
run the exact-ref interface gate, retain a credentialed saved plan, and close the connected gates
in [production activation gates](../../docs/production-activation-gates.md).

## Dedicated runner-pool handoff

`5-workloads/ci/nodepools/runner` owns the on-demand node pool for untrusted runner pods. It exposes
the label `mindclade.dev/workload-class=arc-runner` and the taint
`scheduling.mindclade.dev/arc-runner=true:NoSchedule`. GitOps runner values must select that label
and carry only the matching toleration; the ARC controller must retain neither and stay on the
system pool.

Apply the infrastructure runner pool before reconciling the paired GitOps placement change.
`minRunners: 0` is not a rollout guard: an active scale set can scale from zero when a job queues,
and its pod will remain Pending if the selected pool is absent. Validate the paired checkouts before
approval:

```sh
make validate-gitops-integration GITOPS=../gitops
```

The six-node pool ceiling covers the currently declared artifact-authority request concurrency.
The dormant presubmit target adds up to 24 runners and must not activate until a reviewed
infrastructure change, quota/cost analysis, and connected scheduling test qualify a larger bound.
