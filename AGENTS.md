# Agent operating guide

## Purpose and authority

This repository owns normal Google Cloud organization, environment, network, project, GKE, data
service, and security infrastructure after Ring 0. Read BLUEPRINT.md, README.md,
CONTRIBUTING.md, and docs/dependency-graph.md before editing. Bootstrap owns Ring 0; gitops owns
all in-cluster desired state; reusable Terraform modules belong in mindclade-internal-monorepo.

## Working rules

- Preserve the 1-org through 5-workloads dependency direction and keep environments isolated.
- Pin module sources immutably. Never bypass a missing or incompatible module release by
  vendoring or loosening the reference.
- Keep Argo CD units limited to cloud prerequisites. Do not install Argo CD or Kubernetes
  applications from Terraform.
- Never run apply, import, destroy, state mutation, IAM mutation, cluster mutation, or a
  production plan from an agent session.
- Do not print account contracts, Terraform state/plans, credentials, kubeconfigs, partner data,
  or restricted identifiers.

## Validation

    nix develop .#ci --command make validate
    nix develop .#ci --command make validate-integration MONOREPO=../mindclade-internal-monorepo
    nix flake check --no-update-lock-file

Connected Terragrunt plans, GKE/IAM behavior, VPC Service Controls, Binary Authorization, backup,
and restore drills remain protected qualification gates.

## Done

Local and cross-repository module contracts pass, changed units have a deterministic plan path,
destructive risk and rollback are explicit, and no source-only result is labeled as a live
qualification.
