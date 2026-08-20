# ARC cloud foundation

This tree creates the private, regional GKE cluster and dedicated VPC used only by GitHub ARC
artifact-authority runners. It owns cloud resources, node identity, networking, and IAM. The
`gitops` repository exclusively owns the Kubernetes and Argo CD desired state installed on the
cluster.

The cluster is source-staged and must not be applied until monorepo `v0.2.0` exists, the
bootstrap `1.3.0` contract is applied, GitHub App installation scopes match governance, and a
reviewed connected plan proves that no public endpoint, public node IP, cross-capability
impersonation, or Buildkite authority is created.
