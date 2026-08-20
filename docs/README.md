<!-- mindclade-doc: documentation-home@1 -->

# Mindclade · Infrastructure Live documentation

> **Platform Foundation · Google Cloud operations**  
> Architecture, contracts, activation controls, cross-repository handoffs, and recovery
> procedures for `mindclade/infrastructure-live`.

| Need | Document | Page type |
| --- | --- | --- |
| Understand repository boundaries | [Architecture](architecture.md) | Architecture |
| Understand apply order | [Dependency graph](dependency-graph.md) | Architecture reference |
| Understand state isolation | [State boundaries](state-boundaries.md) | Reference |
| Use a Terraform module safely | [Module interface contract](module-interface-contract.md) | Contract |
| Import and activate the repository | [Initial import](initial-import.md) | How-to |
| Qualify production | [Production activation gates](production-activation-gates.md) | Checklist |
| Hand cloud prerequisites to GitOps | [GitOps handoff](gitops-handoff.md) | Contract |
| Hand automation identities to control planes | [Automation identity handoff](automation-identity-handoff.md) | Contract |
| Understand signer separation | [Supply-chain signer contract](supply-chain-signer-contract.md) | Contract |
| Operate public domains and DNS | [DNS domains](dns-domains.md) | Reference |
| Diagnose or recover service | [Runbooks](runbooks/README.md) | Runbook index |
| Understand the complete platform | [Enterprise platform blueprint](MINDCLADE_ENTERPRISE_PLATFORM_FOUNDATION_BLUEPRINT.md) | Blueprint |

Before applying, identify the state unit, privilege scope, dependencies, protected
environment, and recovery procedure. For incidents, start from the runbook index rather than
running an unreviewed local apply.
