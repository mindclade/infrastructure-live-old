# Developer workstation — development

One private x86_64-linux NixOS instance, reachable only through IAP TCP forwarding. It provides
the Linux build host needed by packages that an aarch64-darwin laptop cannot produce and keeps
long-running work inside `tmux` when the local tunnel disconnects.

## Immutable image boundary

The workstation does not install Debian packages, Nix, or operational tooling at runtime. The
monorepo builds an immutable NixOS GCE raw disk containing Nix, Git, tmux, the Google guest agent,
and the idle-shutdown service. The protected reusable workflow may publish only a
content-addressed `.tar.gz` object and its source/contract digests to the create-only source
bucket. It cannot create or select a Compute Image.

`5-workloads/development/workstation-image` is the sole Compute Image authority. Terraform
requires the exact HTTPS source object, Cloud Storage generation, raw-disk digest, embedded image
contract digest, and CMEK key. This unit then consumes only the resulting immutable image
self-link and contract digest; image families and caller startup scripts are rejected by the
module.

## Source state and activation

The source path is implemented but activation remains fail-closed. Before any workstation apply:

1. apply bootstrap contract `1.6.0` and its exact workstation-image WIF provider;
2. publish reviewed workflow contract `v5.0.0` and Terraform module release `v0.4.0`;
3. apply the access-log and create-only source buckets, then the publisher identity;
4. run the exact-main image workflow and retain the object generation and both digests;
5. inject those four values into the protected infrastructure plan and apply the Compute Image;
6. prove first boot, embedded-contract verification, idle shutdown, cache access under enforced
   VPC Service Controls, and rollback to the previous exact image before selecting the instance.

The authoritative status and evidence gates live in
[`contracts/workstation-egress.json`](../../../contracts/workstation-egress.json). Source
validation passing does not assert that the workflow tag, module tag, buckets, object, image, or
instance exists.

## Network and state boundaries

- The IAP ingress rule is owned by `3-networks/development/firewall-baseline` because the
  instance is in a Shared VPC service project. The exact network tag joins the two states.
- No public egress destination is added. The default deny and reviewed destination inventory are
  enforced repository-wide by `scripts/validate_workstation_egress.py`.
- The persistent data disk stores workspace and Bazel data only. The Nix store belongs to the
  immutable boot image, so image rollback does not mutate developer data.
- Cache grants remain in the bucket-owning CI states; this unit must not claim their IAM bindings.
