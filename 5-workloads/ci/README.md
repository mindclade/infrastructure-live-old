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
`5-workloads/ci/nodepools/runner-spot` is a separate, zero-floor, eight-node source proposal for the
24-runner presubmit target. It uses `mindclade.dev/workload-class=arc-presubmit-spot`, the explicit
presubmit taint, and the module-managed Spot taint, so no current scale set can schedule there.
Do not apply it until GitOps adds a separately reviewed presubmit scale set with both tolerations,
job routing distinguishes eviction from test failure, and quota, cost, eviction, drain, and
on-demand rollback evidence are qualified. Release/signing lanes remain on the on-demand pool.

## Workstation image source authority

`5-workloads/ci/workstation-image-source` is the create-only raw-disk publication boundary for
the immutable development NixOS workstation. It is CMEK protected, versioned, access logged to a
separate locked bucket, and retains objects for one year. Only the dedicated
`workstation-image-pub` identity may create objects; the development Compute service agent may
read the exact object so Terraform can create a Compute Image.

This bucket is not a Compute Image authority. The protected workflow records the HTTPS source
URI, object generation, raw-disk SHA-256, and embedded image-contract SHA-256. A separately
reviewed `5-workloads/development/workstation-image` plan consumes those exact values and creates
the CMEK Compute Image. Missing or mutable evidence blocks that plan.
