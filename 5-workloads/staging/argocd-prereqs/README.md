# Argo CD cloud prerequisites

This directory deliberately contains no Terraform unit. The environment's GKE cluster,
Workload Identity bindings, Secret Manager containers, and private networking are created by
the sibling infrastructure units. The Argo CD installation, configuration, AppProjects, and
upgrades are owned exclusively by the `gitops` repository.

Adding a `terragrunt.hcl` here requires a distinct cloud resource that is not already owned by
another unit. It must never install Kubernetes manifests or a second GKE cluster.
