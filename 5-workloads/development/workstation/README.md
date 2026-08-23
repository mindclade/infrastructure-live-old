# Developer workstation — development

One x86_64-linux instance, reachable only through IAP TCP forwarding, that exists so somebody can
build `remote-execution-base`. That Nix package is gated `optionalAttrs
pkgs.stdenv.hostPlatform.isLinux`, so an aarch64-darwin laptop cannot produce it.

## Provisioning does not complete today

Applying this unit produces a running instance that never finishes its startup script.

`3-networks/development/firewall-baseline` denies egress by default at priority 65000 and allows
only intra-VPC, `restricted.googleapis.com`, and the metadata server. The module's startup script
runs `apt-get update` against Debian's public mirrors and fetches the Nix installer from
`nixos.org`. Both are blocked, and the script runs under `set -euo pipefail`.

The script stops at `apt-get update`, which is after the disk work. What you get:

| Works | Does not exist |
|---|---|
| The instance boots and IAP SSH connects | Nix |
| The CMEK data disk is formatted, mounted, and bound at `/nix` | `tmux`, `git`, `curl`, `xz-utils` |
| OS Login, the dedicated identity, the firewall tag | The idle-shutdown timer |

The last row is the expensive one. The idle timer is installed after the blocked fetches, so the
machine does not power itself off; it bills until the 03:00 stop schedule regardless of use.

## Why this is not fixed here

`var.metadata` refuses the module-owned startup-script key, and no other input on the
`workstation` module changes where those two fetches point. Nothing this caller can write moves
them, so the fix is not a change to this unit.

`contracts/workstation-egress.json` records the reviewed target, the alternatives that were
evaluated and refused, and the evidence that would clear the gate.
`scripts/validate_workstation_egress.py` enforces it, and in particular enforces the thing this
gate is under pressure to break: no egress allow rule in `3-networks` may name a destination the
contract has not already reviewed, and the default deny may not move.

The target adds no egress destination at all. Everything first boot needs comes from inside the
perimeter over the restricted Google API VIP the firewall already allows — apt from an Artifact
Registry APT remote repository, which `3-networks/shared/dns-hub` already resolves through
`*.pkg.dev`, and Nix from the boot image rather than from the network. Closing it needs an
`artifact_registry_factory` that can express a remote APT repository, a `workstation` module whose
startup script reads from internal sources, and an image that carries Nix. All three are monorepo
changes.

## Related boundaries

- The IAP ingress rule is owned by `3-networks/development/firewall-baseline`, not by this unit,
  because the instance lives in a Shared VPC service project. The network tag is the join; renaming
  it on one side produces an instance that passes every IAM check and then times out at connect.
- Cache grants are applied by the owning `5-workloads/ci` units, which expose member inputs. Two
  states claiming one bucket binding is how removing one revokes access the other still claims.
- `5-workloads/development/vpc-sc-perimeter` restricts `storage.googleapis.com` and
  `artifactregistry.googleapis.com` while the caches live in `mc-common-ci`, outside the perimeter.
  Those reads are logged rather than denied only because the perimeter is in explicit dry-run.
