# GitOps handoff

Before an environment is handed to GitOps, infrastructure-live guarantees that the cluster,
private network, workload identity, registry, Secret Manager resources, KMS, admission trust,
storage, databases, backup, and observability prerequisites exist.

Terraform does not install Argo CD. The GitOps repository applies the pinned Argo CD bootstrap
manifest and root application once; Argo CD then self-manages from Git.
