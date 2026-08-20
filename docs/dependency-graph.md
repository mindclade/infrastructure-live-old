# Dependency Graph and Apply Order

The numeric tree is an enforced dependency contract, not cosmetic organization.

```text
bootstrap (external Ring 0)
   |
   v
1-org
   |
   v
2-environments
   |
   v
3-networks
   |
   v
4-projects
   |
   v
5-workloads
   |
   v
gitops (external Kubernetes desired state)
```

A dependency may point within its layer or to a lower numbered layer. Cross-environment
references are prohibited except explicitly shared resources under `3-networks/shared` and
organization/common resources under `1-org`.

## Key edges

| Consumer | Dependency | Purpose |
|---|---|---|
| `1-org/common-projects` | `1-org/folders` | Place common projects in the common folder |
| `2-environments/<env>/folders` | `1-org/folders` | Create domain child folders |
| `2-environments/<env>/shared-projects` | `1-org/folders` | Create environment host/foundation projects |
| `3-networks/<env>/shared-vpc-host` | environment shared projects | Host-project identity |
| `4-projects/<env>/<domain>` | environment folders and Shared VPC | Project placement and attachment |
| `5-workloads/<env>/gke` | environment project, VPC, and KMS | Private cluster foundation |
| `5-workloads/<env>/nodepools/*` | GKE | Cluster attachment |
| `5-workloads/<env>/binary-authorization` | GKE and organization attestor/KMS | Admission trust |
| `5-workloads/<env>/storage/*` | domain projects and networking | Data-plane ownership |
| `3-networks/shared/public-zones/*` | common DNS project | Authoritative public DNS |

`5-workloads/<env>/argocd-prereqs` is documentation/cloud handoff only. Argo CD installation
and reconciliation are exclusively owned by `gitops`.

## CI execution

CI uses modern dependency-aware commands with strict mode:

```sh
TG_STRICT_MODE=true terragrunt run --all --non-interactive -- plan
```

The protected apply workflow saves plans with Terragrunt `--out-dir` and applies the same
plans after environment approval. External dependencies are read from remote state and are
not implicitly applied with another privilege scope.

## Recovery

Rebuild in numeric order. Destroy in reverse order. Critical projects, KMS, stateful storage,
and production clusters require an explicit decommission procedure before deletion protection
is removed.
