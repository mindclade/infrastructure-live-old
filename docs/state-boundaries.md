<!-- mindclade-doc: reference@1 -->

# State boundaries

> **Audience:** platform engineers reviewing or recovering Terragrunt state.
> **Outcome:** identify the authoritative state unit, bucket, and permitted dependency direction
> before planning or applying a change.

Each directory containing `terragrunt.hcl` is an independently locked state unit. This keeps
blast radius and recovery work scoped to one resource boundary; never merge units by copying
their state objects or backend prefixes.

## Storage model

| Unit location | State bucket class | Isolation rule |
|---|---|---|
| Organization, shared, and production | `infrastructure-live-production` | Independent object prefix and lock |
| Development | Development bucket | No dependency on staging or production state |
| Staging | Staging bucket | No dependency on production state |

Bucket names and prefixes are computed by [`root.hcl`](../root.hcl). Treat that file and the
resolved Terragrunt configuration as authoritative; do not infer a backend from directory names
alone.

## Dependency rules

- Dependencies flow from lower-numbered layers to higher-numbered layers.
- Cross-environment dependencies are prohibited.
- Shared outputs may be consumed only through declared Terragrunt dependencies.
- Mock outputs are validation aids and must not become production configuration.
- State objects are never committed or attached to issues.
- Plans are short-lived, access-controlled CI artifacts and are treated as sensitive.

The repository validates dependency order with:

```sh
python3 scripts/validate-dependency-order.py
```

Run the complete repository contract before review:

```sh
nix develop .#ci --command make validate
```

## Recovery

Stop every operation for the affected unit before recovery. For an orphaned lock, follow
[Terraform state lock appears stuck](runbooks/state-lock-stuck.md). For reconstruction or import,
follow [initial import](initial-import.md) and retain the exact state prefix, generation, source
commit, operator, and plan evidence in the incident record.
