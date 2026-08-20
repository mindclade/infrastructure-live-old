<!-- mindclade-doc: reference@1 -->

# Staging Argo CD cloud prerequisites

> **Purpose:** record the staging ownership boundary; this directory is intentionally not a
> Terraform state unit.

This directory deliberately contains no Terraform unit. The environment's GKE cluster,
Workload Identity bindings, Secret Manager containers, and private networking are created by
the sibling infrastructure units. The Argo CD installation, configuration, AppProjects, and
upgrades are owned exclusively by the `gitops` repository.

Adding a `terragrunt.hcl` here requires a distinct cloud resource that is not already owned by
another unit. It must never install Kubernetes manifests or a second GKE cluster.

Before activation, verify the staging cluster, network, workload identity, Secret Manager,
artifact, policy, backup, and observability prerequisites through their owning units. Then follow
the [GitOps handoff](../../../docs/gitops-handoff.md). A successful handoff leaves Terraform with no
Argo-managed Kubernetes resources in its plan.
