<!-- mindclade-doc: repository-home@2 -->
<!-- Brand source: mindclade/.github-private/mindclade-brand-assets (MONO family). -->

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/mono-wordmark-dark-1080w.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/brand/mono-wordmark-1080w.png">
    <img alt="Mindclade." src="docs/assets/brand/mono-wordmark-1080w.png" width="360">
  </picture>
</p>

<p align="center">
  <img alt="class: production-control" src="docs/assets/badges/repository-class.svg">
  <img alt="visibility: private" src="docs/assets/badges/visibility.svg">
  <img alt="change: pull-request" src="docs/assets/badges/change-model.svg">
  <img alt="stack: Terraform + Terragrunt" src="docs/assets/badges/stack.svg">
</p>

# Mindclade · Infrastructure Live

> **Platform Foundation · Google Cloud desired state**
> Operate the normal cloud estate through isolated Terraform state and an explicit Terragrunt
> dependency graph after Ring 0 is established.

| Repository contract | Value |
| --- | --- |
| Class | `production-control` |
| Visibility | `private` |
| Change model | `pull-request` |
| Authority | `normal-gcp-organization-infrastructure`<br>`folders`<br>`org-policy`<br>`environments`<br>`networks`<br>`projects`<br>`gke`<br>`managed-cloud-services` |
| Primary readers | Cloud platform, security, and reliability engineers |
| First success | [Validate the live estate source](#quick-start) |
| Start here | [`docs/README.md`](docs/README.md) |

## Mission

`infrastructure-live` is the authoritative normal-plane Google Cloud configuration. Platform
engineers use its numbered Terragrunt layers to create organization controls, environments,
networks, projects, GKE, and managed services with independent state boundaries.

## Authority boundary

### This repository creates

- Organization hierarchy and policy after the bootstrap boundary.
- Development, staging, and production foundations, networks, and workload projects.
- GKE and managed cloud services, cloud-side workload identities, and GitOps prerequisites.

### This repository deliberately does not create

- Ring-0 state, initial federation, or break-glass recovery; those remain in `bootstrap`.
- Argo CD installation, Kubernetes objects, or application selection; those remain in `gitops`.
- Application source or reusable Terraform modules; those remain in the monorepo.

## Quick start

Prerequisite: Nix with flakes enabled. This validation needs no Google Cloud credentials and
does not read state or create a plan.

```sh
nix develop .#ci --command make validate
nix flake check --no-update-lock-file
```

**Success means:** repository contracts, account and module interfaces, layer dependencies,
Terraform/Terragrunt syntax, DNS portfolio, and tests all pass.

**If it fails:** begin with the earliest failing numbered layer and use the
[dependency graph](docs/dependency-graph.md) to resolve upstream contracts before downstream
units.

**Safety boundary:** do not run an apply, import, destroy, state operation, or production plan
from an agent or ordinary development session.

## Estate position

The highlighted node is this repository. The contract and boundary sections preserve the
diagram's authority model when Mermaid is unavailable.

```mermaid
%% current: infrastructure-live %%
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#F2EFE8","primaryTextColor":"#201C24","primaryBorderColor":"#B5673F","secondaryColor":"#FBFAF7","tertiaryColor":"#FBFAF7","lineColor":"#5B5660","edgeLabelBackground":"#FBFAF7","clusterBkg":"#FBFAF7","clusterBorder":"#E2DED4"}}}%%
flowchart LR
    GHP[".github-private<br/>profile + brand"] --> GH[".github<br/>shared workflows"]
    GH --> GC["github-config<br/>GitHub governance"]
    GH --> BS["bootstrap<br/>Ring 0 trust"]
    BS --> IL["infrastructure-live<br/>cloud foundation"]
    IL --> GO["gitops<br/>cluster desired state"]
    MO["internal monorepo<br/>source + evidence"] --> GO
    GC --> MO
    classDef current fill:#201C24,color:#F2EFE8,stroke:#D68A61,stroke-width:3px;
    classDef managed fill:#F2EFE8,color:#201C24,stroke:#B5673F,stroke-width:1.5px;
    classDef source fill:#FBFAF7,color:#423D48,stroke:#5B5660,stroke-width:1.5px;
    class IL current;
    class GH,GC,BS,GO managed;
    class GHP,MO source;
```

## Repository map

| Path | Purpose |
| --- | --- |
| `1-org/` | Organization hierarchy, policy, logging, and common controls. |
| `2-environments/` | Development, staging, and production foundations. |
| `3-networks/` | Shared VPC, DNS, NAT, firewall, and connectivity. |
| `4-projects/` | Domain and partner workload projects. |
| `5-workloads/` | GKE and managed cloud services. |
| `_envcommon/` | Shared reviewed inputs; it creates no resources. |
| `contracts/` | Account, handoff, DNS, and repository contracts. |

## Change path

Pull requests run validation and affected speculative plans. After merge, protected workflows
create saved plans for the exact commit, select the minimum privilege scope, require the
matching environment approval, and apply the verified plan. Destructive changes require an
explicit reviewed dispatch and change reference. See the
[dependency graph](docs/dependency-graph.md) and [activation gates](docs/production-activation-gates.md).

## Documentation and support

- [Documentation home](docs/README.md)
- [Architecture](docs/architecture.md)
- [State boundaries](docs/state-boundaries.md)
- [GitOps handoff](docs/gitops-handoff.md)
- [Runbooks](docs/runbooks/README.md)
- [Contributing](CONTRIBUTING.md)
- Policies and terms: [governance](GOVERNANCE.md) · [conduct](CODE_OF_CONDUCT.md) ·
  [support](SUPPORT.md) · [legal](LEGAL.md) · [license](LICENSE) · [notice](NOTICE) ·
  [changes](CHANGELOG.md)

## Security

Never expose state, plans, account contracts, credentials, kubeconfigs, partner data, or
restricted identifiers. Use [the private security process](SECURITY.md) for vulnerabilities.
