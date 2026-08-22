## Infrastructure outcome

Describe the affected units, environments, dependency edges, and intended
operator-visible result.

## Risk and authority

- Change class: routine / high / critical
- Availability, security, privacy, cost, or data impact:
- Creates, replacements, and destroys:
- Production activation gate or change record:
- Required approvers:

## Validation evidence

List exact commands and results. Link access-controlled plan artifacts; never
paste state or raw plan values.

```text
nix develop --command make validate
```

## Rollback and recovery

Describe migration ordering, rollback, observable success, and recovery if the
next dependency or protected apply environment is unavailable.

## Checklist

- [ ] Every consumed output has an explicit Terragrunt dependency.
- [ ] Modules are pinned to immutable approved versions.
- [ ] The exact reviewed main SHA will be planned and applied through the protected environment.
- [ ] No credential, state, plan, customer data, or incident evidence is committed.
- [ ] Production changes have Platform and Security review and two qualified approvals.

## Contributor authorization

- [ ] I am authorized under a current written agreement with Mindclade, LLC. to
      submit every part of this contribution.
- [ ] I identified every third-party component, specification, or generated
      artifact and preserved its source, license, provenance, and notices.
- [ ] I updated `LICENSE`, `NOTICE`, the SBOM, or other license evidence when
      the included or distributed material changed.
