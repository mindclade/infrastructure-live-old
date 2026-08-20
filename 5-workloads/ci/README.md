# ARC cloud foundation

This tree creates the private, regional GKE cluster and dedicated VPC used only by GitHub ARC
artifact-authority runners. It owns cloud resources, node identity, networking, and IAM. The
`gitops` repository exclusively owns the Kubernetes and Argo CD desired state installed on the
cluster.

The network and admission modules pin immutable qualified commit
`164f2998f9540243a0df769dc78c96677134c70a`. The GKE and artifact-registry units remain
fail-closed on the planned `v0.2.0` ref until secret synchronization and service-agent CMEK
support are released. Apply neither path until
bootstrap contract `1.3.0` is applied, GitHub App scopes match governance, and a reviewed
connected plan proves that no public endpoint, public node IP, cross-capability impersonation,
or retired Buildkite authority is created.
