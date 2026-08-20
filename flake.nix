# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

{
  description = "Toolchain for mindclade infrastructure-live";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true; # Terraform is BUSL-licensed since 1.6
        };

        # -----------------------------------------------------------------------------------
        # Terragrunt 1.1.2, pinned by hash rather than taken from nixpkgs
        # -----------------------------------------------------------------------------------
        # nixos-25.05 ships terragrunt 0.78.2, and the gap is not cosmetic — this repository
        # is written against 1.0:
        #
        #   `exclude { }` blocks          1.0 replaced the old `skip = true` attribute
        #   `errors { retry { } }`        in root.hcl; does not exist in 0.78
        #   Terragrunt's modern dependency-aware execution is `terragrunt run --all`.
        #
        # So the nixpkgs build would fail every unit in the repository, not merely differ.
        # Rather than downgrade the configuration to match the package, the exact release is
        # fetched here with its published SHA256 recorded inline.
        #
        # This keeps the property the whole change is for: nothing is executed that has not
        # been checked against a hash committed to this repository. `fetchurl` refuses to
        # produce the derivation if the bytes do not match, which is the same guarantee the
        # nixpkgs store paths give — just with the expected value written down here.
        #
        # Checksums are from the release's own SHA256SUMS, which is additionally cosign-signed
        # upstream (SHA256SUMS.sig / .pem):
        #   curl -fsSL https://github.com/gruntwork-io/terragrunt/releases/download/v1.1.2/SHA256SUMS
        #
        # Bumping the version means changing BOTH the version and the two hashes. A wrong hash
        # fails the build loudly; there is no path where a mismatched binary runs.
        terragruntVersion = "1.1.2";
        terragruntSha = {
          x86_64-linux = "534070d5b261a0e65b3f490479f602a8f80a0ae115e399a3786802cce658aeaa";
          aarch64-darwin = "f3e6418181699e14ea282257e36ea6be3949ff9ebd4854eff6bd2fe51130791a";
        };
        terragruntAsset = {
          x86_64-linux = "terragrunt_linux_amd64";
          aarch64-darwin = "terragrunt_darwin_arm64";
        };

        terragrunt-pinned =
          if !(terragruntSha ? ${system}) then
          # Fail at evaluation with a message that says what to do, rather than silently
          # falling back to the nixpkgs version and breaking every unit at apply time.
            throw "terragrunt ${terragruntVersion} is not pinned for ${system}; add its SHA256 from the release's SHA256SUMS to flake.nix"
          else
            pkgs.runCommand "terragrunt-${terragruntVersion}"
              {
                src = pkgs.fetchurl {
                  url = "https://github.com/gruntwork-io/terragrunt/releases/download/v${terragruntVersion}/${terragruntAsset.${system}}";
                  sha256 = terragruntSha.${system};
                };
                nativeBuildInputs = pkgs.lib.optional pkgs.stdenv.isLinux pkgs.autoPatchelfHook;
                meta.mainProgram = "terragrunt";
              } ''
              install -Dm755 "$src" "$out/bin/terragrunt"
            '';

        # -----------------------------------------------------------------------------------
        # Terraform 1.15.9, pinned by hash for the same reason as terragrunt
        # -----------------------------------------------------------------------------------
        # nixos-25.05 ships terraform 1.12.0, not the 1.15.9 that .terraform-version and every
        # setup-terraform step pin — so `nix develop` handed a laptop a different binary than
        # CI runs, and the shellHook below would warn on every single shell entry. A warning
        # that fires every time stops being read.
        #
        # Pinning it here makes local and CI the same build and removes the last place the
        # toolchain version had two answers. Checksums from the release's own SHA256SUMS:
        #   curl -fsSL https://releases.hashicorp.com/terraform/1.15.9/terraform_1.15.9_SHA256SUMS
        terraformVersion = "1.15.9";
        terraformSha = {
          x86_64-linux = "76edd0b22d2f27d3d2e097cd793209646f719cf60f02ff3af626b07361137da1";
          aarch64-darwin = "05b27586a5d7d84105690ecccc7edbbf48bc3d6d577745cb61f163ba990adf4f";
        };
        terraformPlatform = {
          x86_64-linux = "linux_amd64";
          aarch64-darwin = "darwin_arm64";
        };

        terraform-pinned =
          if !(terraformSha ? ${system}) then
            throw "terraform ${terraformVersion} is not pinned for ${system}; add its SHA256 from the release SHA256SUMS to flake.nix"
          else
            pkgs.runCommand "terraform-${terraformVersion}"
              {
                src = pkgs.fetchurl {
                  url = "https://releases.hashicorp.com/terraform/${terraformVersion}/terraform_${terraformVersion}_${terraformPlatform.${system}}.zip";
                  sha256 = terraformSha.${system};
                };
                nativeBuildInputs = [ pkgs.unzip ]
                  ++ pkgs.lib.optional pkgs.stdenv.isLinux pkgs.autoPatchelfHook;
                meta.mainProgram = "terraform";
              } ''
              unzip -q "$src"
              install -Dm755 terraform "$out/bin/terraform"
            '';
      in
      {
        # ---------------------------------------------------------------------------------
        # CI shell
        # ---------------------------------------------------------------------------------
        # Terragrunt only.
        #
        # It was previously fetched with `curl -fsSL -o /usr/local/bin/terragrunt` in five
        # places across plan.yml, apply.yml, and drift.yml, with nothing verifying the bytes —
        # in the repository that applies the whole GCP estate. flake.lock pins the nixpkgs
        # revision and Nix checks every store path against its hash, so the download is gone
        # rather than merely authenticated.
        #
        # NO terraform here, deliberately. The workflows get it from the SHA-pinned
        # hashicorp/setup-terraform action, which is not an unverified download; putting it in
        # this shell as well would leave two terraform binaries on PATH with the order
        # deciding which one runs.
        #
        # Separate from `default` because that shell also carries google-cloud-sdk, checkov and
        # infracost — a large closure to realise for a job that needs one binary.
        devShells.ci = pkgs.mkShell {
          packages = [ terragrunt-pinned ] ++ (with pkgs; [
            # The `lint` job in plan.yml. .yamllint.yaml and .github/actionlint.yaml were in
            # this repository with nothing running either of them — and only `default` carried
            # the binaries, which is a shell no workflow resolves.
            actionlint
            shellcheck # actionlint shells out to it for `run:` blocks
            yamllint
          ]);
        };

        devShells.default = pkgs.mkShell {
          # Every version here is fixed by flake.lock, which is committed. Without it
          # `nixos-25.05` is a BRANCH resolved at evaluation time, and the toolchain would
          # drift between a laptop and CI with no file in this repository changing.
          packages = with pkgs; [
            google-cloud-sdk
            jq
            gh
            tflint
            checkov
            infracost
            shellcheck
            yamllint
            actionlint

            terraform-pinned

            # The same hash-pinned 1.1.2 the CI shell uses. nixpkgs' 0.78.2 would parse none
            # of this repository's units — see the derivation above.
            terragrunt-pinned

            # bash 5, explicitly.
            #
            # scripts/plan-changed.sh uses `declare -A` and `mapfile`, both bash 4+. macOS
            # ships bash 3.2 and will never ship newer, so on a laptop without this the
            # script fails with "mapfile: command not found" — while CI, on ubuntu, passes.
            # A script that only works in CI is a script nobody can debug.
            bashInteractive
          ];

          shellHook = ''
            # ---------------------------------------------------------------------------
            # Toolchain version check
            # ---------------------------------------------------------------------------
            # nixpkgs is pinned to a channel, so this shell IS reproducible — but the channel
            # decides the terraform version, and nothing made it agree with the 1.15.9 that
            # .terraform-version, TF_VERSION, and every setup-terraform step pin.
            #
            # Pinning a specific terraform build here would mean a nixpkgs overlay per tool.
            # Checking is cheaper and catches the thing that actually goes wrong: a plan that
            # succeeds locally and fails in CI on a state-file version mismatch, which reads
            # like state corruption.
            want_tf="$(tr -d '[:space:]' < .terraform-version 2>/dev/null || echo unknown)"
            have_tf="$(terraform version -json 2>/dev/null | jq -r .terraform_version 2>/dev/null || echo unknown)"

            want_tg="$(tr -d '[:space:]' < .terragrunt-version 2>/dev/null || echo unknown)"
            have_tg="$(terragrunt --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo unknown)"

            echo "infrastructure-live"
            echo "  terraform  $have_tf (pinned $want_tf)"
            echo "  terragrunt $have_tg (pinned $want_tg)"

            if [ "$have_tf" != "$want_tf" ] && [ "$want_tf" != "unknown" ]; then
              echo
              echo "  WARNING: terraform $have_tf does not match .terraform-version ($want_tf)."
              echo "           CI runs $want_tf. A newer local binary writes a state file the"
              echo "           CI version refuses to read, and the error reads like corruption."
              echo "           Bump the nixpkgs channel, or use the pinned version directly."
            fi
            if [ "$have_tg" != "$want_tg" ] && [ "$want_tg" != "unknown" ]; then
              echo
              echo "  WARNING: terragrunt $have_tg does not match .terragrunt-version ($want_tg)."
            fi

            echo
            echo "  ./scripts/plan-changed.sh    plan only what this branch touches"
            echo "  docs/dependency-graph.md     apply order between stages"
          '';
        };
      });
}
