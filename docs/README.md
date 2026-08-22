<!-- mindclade-doc: documentation-home@1 -->

# Mindclade · Infrastructure Live documentation

> **Platform Foundation · Google Cloud operations**  
> Understand, activate, operate, and recover Mindclade's layered Google Cloud desired state.

## Choose your path

| If you need to... | Start with | You will... |
| --- | --- | --- |
| Understand the cloud control plane | [Architecture](architecture.md) | Learn authority, state, trust, and failure boundaries |
| Determine safe apply order | [Dependency graph](dependency-graph.md) | Identify unit dependencies and CI execution order |
| Import or activate existing resources | [Initial import](initial-import.md) | Reconcile state before protected mutation |
| Qualify production | [Production activation gates](production-activation-gates.md) | Collect required cloud, identity, and recovery evidence |
| Publish vulnerability contact metadata | [security.txt publication](runbooks/security-txt-publication.md) | Serve and renew exact RFC 9116 files on every controlled HTTPS origin |
| Diagnose or recover an incident | [Runbooks](runbooks/README.md) | Start from an observable failure and preserve state |

## Getting started

- [Initial import and activation](initial-import.md) — generate the account contract, import
  existing resources, and activate scopes in dependency order.
- [Production activation gates](production-activation-gates.md) — prove readiness before the
  first production mutation.
- [Dependency graph](dependency-graph.md) — understand layer and unit ordering before planning.

## Concepts and architecture

- [Architecture](architecture.md) — repository boundary, apply flow, and failure domains.
- [State boundaries](state-boundaries.md) — state isolation, bucket selection, and prohibited
  cross-environment dependencies.
- [Module interface contract](module-interface-contract.md) — immutable module references and
  preflight behavior.
- [DNS domains](dns-domains.md) — registrar, authoritative DNS, mail, and delegation ownership.
- [security.txt publication](runbooks/security-txt-publication.md) — generated contact files,
  HTTPS-origin activation, connected evidence, renewal, and rollback.

## Handoffs and component boundaries

- [GitOps handoff](gitops-handoff.md) — cloud prerequisites required before Argo activation.
- [Automation identity handoff](automation-identity-handoff.md) — Ring-0 and normal-plane
  identity ownership.
- [Supply-chain signer contract](supply-chain-signer-contract.md) — builder, qualifier, signer,
  and admission separation.
- [Environment automation IAM](../1-org/automation-iam/README.md) — plan/apply folder scope.
- [Common CI Bazel cache](../5-workloads/ci/bazel-remote-cache/README.md) — source-only identity,
  storage, activation, and client-semantics handoff.
- [Authoritative DNS project](../3-networks/shared/dns-project/README.md) — shared project
  ownership without duplicate creation.
- [Partner projects](../4-projects/partners/README.md) — activation and isolation requirements.
- [Control-plane identities](../5-workloads/shared/control-plane-identities/README.md) — GitOps
  render/verifier identities and secret-container boundary.
- Argo CD cloud prerequisites: [development](../5-workloads/development/argocd-prereqs/README.md),
  [staging](../5-workloads/staging/argocd-prereqs/README.md), and
  [production](../5-workloads/production/argocd-prereqs/README.md).
- IAP activation handoffs: [development](../5-workloads/development/iap-access/README.md),
  [staging](../5-workloads/staging/iap-access/README.md), and
  [production](../5-workloads/production/iap-access/README.md).

## Operations

- [Runbook index](runbooks/README.md) — Binary Authorization, failed apply, GKE reconstruction,
  state lock, and VPC Service Controls recovery.
- [Production activation gates](production-activation-gates.md) — evidence record and
  high-availability gate.

## Reference and governance

- [Repository production blueprint](../BLUEPRINT.md) — compact authority and exclusion contract.
- [Enterprise platform blueprint](MINDCLADE_ENTERPRISE_PLATFORM_FOUNDATION_BLUEPRINT.md) —
  stable pointer to the canonical estate-wide contract.
- [DNS portfolio compatibility path](dns-domain-portfolio.md) — stable path retained for earlier
  references; authoritative content lives in [DNS domains](dns-domains.md).
- [Contributing](../CONTRIBUTING.md) and [security](../SECURITY.md) — review, handling, and
  sensitive-output rules.

## Source of truth

Terragrunt units, `root.hcl`, `_envcommon/`, provider locks, live-tree and dependency validators,
protected workflows, tests, and `contracts/repository.yaml` are authoritative. Documentation
does not replace a reviewed plan or grant production authority.

## Validate documentation changes

Run from the repository root:

```sh
nix develop .#ci --command make validate
```

Check local links, validate examples against the exact unit or script they describe, and preview
rendered Markdown before merge. New pages follow the canonical
[Mindclade documentation templates](https://github.com/mindclade/.github/tree/main/docs/templates).
