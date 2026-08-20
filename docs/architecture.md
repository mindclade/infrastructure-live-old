# Infrastructure-live architecture

This repository owns all normal Google Cloud infrastructure after Ring 0. Its dependency
order is `1-org -> 2-environments -> 3-networks -> 4-projects -> 5-workloads`. A lower-numbered
layer cannot depend on a higher-numbered layer. `bootstrap` owns only state, automation trust,
seed projects, and break-glass recovery. `gitops` owns all Kubernetes/Argo CD desired state.

Global and production units use the bootstrap-created production/foundation state bucket;
development and staging use isolated buckets and apply identities. Every Terragrunt unit has
one state prefix derived from its repository path.
