# Inert CI artifact prerequisite

This subtree currently contains only the private artifact-registry prerequisite. The deferred ARC
VPC, runner cluster, admission policy, runner IAM, and Kubernetes activation are intentionally
absent. Nothing here is reachable from an Argo CD root or authorizes a release.

The registry module uses the repository-wide immutable compatibility bridge documented in
[`docs/module-interface-contract.md`](../../docs/module-interface-contract.md). A future ARC
release must add its cloud, governance, GitOps, identity, and recovery contracts together through
separately reviewed protected plans; source eligibility alone is never activation authority.
