# Mindclade Infrastructure Live

Authoritative Terraform/Terragrunt desired state for Mindclade's normal Google Cloud estate.
Ring‑0 state, initial federation, and break-glass recovery remain in `bootstrap`; Kubernetes
application state remains in `gitops`.

## Authority

This repository owns:

- organization folders, policies, logging, SCC, contacts, and common projects;
- development, staging, production, and partner project foundations;
- Shared VPC, DNS, NAT, firewall policy, PSC, and optional interconnect resources;
- GKE, CPU/GPU node pools, registries, Binary Authorization, storage, databases, backups,
  VPC Service Controls, Secret Manager resources, and cloud-side Argo CD prerequisites.

It does not install Argo CD or other Kubernetes applications and does not store secret values.

## Layering

```text
1-org          organization hierarchy and common controls
2-environments environment foundations and child folders
3-networks     shared and environment network infrastructure
4-projects     domain and partner workload projects
5-workloads    clusters and managed cloud services
```

Dependencies may point only from a higher numbered layer to the same or a lower numbered
layer. Each Terragrunt unit has an independent state prefix.

## Environments

Development, staging, and production use the same architectural shape. Scale, availability,
retention, and accelerator capacity differ intentionally through `env.hcl`; security and
identity boundaries do not silently disappear in lower environments.

The four public domains are hosted in separate Cloud DNS managed zones under
`3-networks/shared/public-zones/`. Squarespace remains the registrar. See
[`docs/dns-domains.md`](docs/dns-domains.md) before changing delegation or DNSSEC.

## Toolchain

```sh
nix develop
make validate
make plan-development
```

The flake pins Terraform 1.15.9 and Terragrunt 1.1.2 by release checksum. CI enables
Terragrunt strict mode.

Generate a local, ignored `.account.env` only from verified `bootstrap` outputs:

```sh
./scripts/bootstrap-account.sh ../bootstrap
```

Do not hand-edit state bucket, WIF, project-number, or bootstrap project values.

## Change flow

Pull requests run format, validation, policy/security checks, affected plans, cost analysis,
and destructive-change classification. After merge, the apply workflow:

1. selects the minimum affected privilege scope;
2. creates saved plans for the exact merged SHA using the plan identity;
3. stores them for one day with a checksum manifest;
4. waits on the corresponding protected GitHub environment;
5. verifies and applies those exact plans using the scope-specific apply identity.

Direct production applies from developer machines are emergency-only and must be reconciled
back to Git.

## Reusable modules

Modules are consumed from `mindclade-internal-monorepo/infra/terraform/modules` using immutable
release references. The interface and qualification contract is documented in
[`docs/module-interface-contract.md`](docs/module-interface-contract.md).

## Operations

- [Architecture](docs/architecture.md)
- [Dependency graph](docs/dependency-graph.md)
- [State boundaries](docs/state-boundaries.md)
- [GitOps handoff](docs/gitops-handoff.md)
- [Automation identity handoff](docs/automation-identity-handoff.md)
- [Failed production apply](docs/runbooks/failed-production-apply.md)
- [Enterprise blueprint](BLUEPRINT.md)
