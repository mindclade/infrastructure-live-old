# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

{
  description = "Toolchain for mindclade infrastructure-live";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs =
    { nixpkgs, ... }:
    let
      # Protected workflows execute on Linux/amd64 and operators use Apple Silicon. The
      # release binaries below are intentionally exposed only where both are checksum-pinned.
      systems = [
        "x86_64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      perSystem =
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfreePredicate = package: nixpkgs.lib.getName package == "terraform";
          };

          # -----------------------------------------------------------------------------------
          # Terragrunt 1.1.2, pinned by hash rather than taken from nixpkgs
          # -----------------------------------------------------------------------------------
          # The release channel is not the version authority for this repository; the exact
          # 1.1.2 pin is, and the gap from older Nixpkgs releases was not cosmetic:
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
            x86_64-linux = "sha256-U0Bw1bJhoOZbP0kEefYCqPgKCuEV45mjeGgCzOZYrqo=";
            aarch64-darwin = "sha256-8+ZBgYFpnhTqKCJX426mvjlJ/569SFTv9r0v5REweRo=";
          };
          terragruntAsset = {
            x86_64-linux = "terragrunt_linux_amd64";
            aarch64-darwin = "terragrunt_darwin_arm64";
          };

          terragruntPinned = pkgs.stdenvNoCC.mkDerivation {
            pname = "terragrunt";
            version = terragruntVersion;
            src = pkgs.fetchurl {
              url = "https://github.com/gruntwork-io/terragrunt/releases/download/v${terragruntVersion}/${terragruntAsset.${system}}";
              hash = terragruntSha.${system};
            };
            dontUnpack = true;
            nativeBuildInputs = pkgs.lib.optional pkgs.stdenv.hostPlatform.isLinux pkgs.autoPatchelfHook;
            installPhase = ''
              runHook preInstall
              install -Dm755 "$src" "$out/bin/terragrunt"
              runHook postInstall
            '';
            meta = with pkgs.lib; {
              description = "Thin orchestration layer for Terraform";
              homepage = "https://terragrunt.gruntwork.io/";
              license = licenses.mit;
              mainProgram = "terragrunt";
              platforms = [ system ];
            };
          };

          # -----------------------------------------------------------------------------------
          # Terraform 1.15.9, pinned by hash for the same reason as terragrunt
          # -----------------------------------------------------------------------------------
          # Keep Terraform at the exact 1.15.9 that .terraform-version and every setup-terraform
          # step pin. Following the channel package would let a routine Nixpkgs update hand a
          # laptop a different state engine than CI runs.
          #
          # Pinning it here makes local and CI the same build and removes the last place the
          # toolchain version had two answers. Checksums from the release's own SHA256SUMS:
          #   curl -fsSL https://releases.hashicorp.com/terraform/1.15.9/terraform_1.15.9_SHA256SUMS
          terraformVersion = "1.15.9";
          terraformSha = {
            x86_64-linux = "sha256-du3Qsi0vJ9PS4JfNeTIJZG9xnPYPAv869iawc2ETfaE=";
            aarch64-darwin = "sha256-BbJ1hqXX2EEFaQ7MzH7bv0i8PW1Xd0XLYfFjupkK308=";
          };
          terraformPlatform = {
            x86_64-linux = "linux_amd64";
            aarch64-darwin = "darwin_arm64";
          };

          terraformPinned = pkgs.stdenvNoCC.mkDerivation {
            pname = "terraform";
            version = terraformVersion;
            src = pkgs.fetchurl {
              url = "https://releases.hashicorp.com/terraform/${terraformVersion}/terraform_${terraformVersion}_${terraformPlatform.${system}}.zip";
              hash = terraformSha.${system};
            };
            dontUnpack = true;
            nativeBuildInputs = [
              pkgs.unzip
            ]
            ++ pkgs.lib.optional pkgs.stdenv.hostPlatform.isLinux pkgs.autoPatchelfHook;
            installPhase = ''
              runHook preInstall
              unzip -q "$src" -d release
              install -Dm755 release/terraform "$out/bin/terraform"
              if [ -f release/LICENSE.txt ]; then
                install -Dm644 release/LICENSE.txt "$out/share/licenses/terraform/LICENSE.txt"
              fi
              runHook postInstall
            '';
            meta = with pkgs.lib; {
              description = "Terraform infrastructure-as-code CLI";
              homepage = "https://www.terraform.io/";
              license = licenses.bsl11;
              mainProgram = "terraform";
              platforms = [ system ];
            };
          };

          validationPython = pkgs.python3.withPackages (pythonPackages: [
            pythonPackages.jsonschema
          ]);

          ciShell = pkgs.mkShell {
            # ---------------------------------------------------------------------------------
            # CI shell
            # ---------------------------------------------------------------------------------
            # Terragrunt with an exact Terraform delegate.
            #
            # It was previously fetched with `curl -fsSL -o /usr/local/bin/terragrunt` in five
            # places across plan.yml, apply.yml, and drift.yml, with nothing verifying the bytes —
            # in the repository that applies the whole GCP estate. flake.lock pins the nixpkgs
            # revision and Nix checks every store path against its hash, so the download is gone
            # rather than merely authenticated.
            #
            # Terraform stays off PATH so workflow steps can continue using setup-terraform directly.
            # Terragrunt does not consult that ambiguous PATH: TG_TF_PATH points at the same
            # hash-pinned Terraform derivation used by the developer shell.
            #
            # Separate from `default` because that shell also carries google-cloud-sdk, checkov and
            # infracost — a large closure to realise for a job that needs one binary.
            TG_TF_PATH = "${terraformPinned}/bin/terraform";

            packages = [
              terragruntPinned
              validationPython
            ]
            ++ (with pkgs; [
              # The `lint` job in plan.yml. .yamllint.yaml and .github/actionlint.yaml were in
              # this repository with nothing running either of them — and only `default` carried
              # the binaries, which is a shell no workflow resolves.
              actionlint
              bind # dig for the read-only DNS cutover evidence workflow
              git
              gnumake
              shellcheck # actionlint shells out to it for `run:` blocks
              yamllint
            ]);
          };

          defaultShell = pkgs.mkShell {
            TG_TF_PATH = "${terraformPinned}/bin/terraform";

            # Every version here is fixed by flake.lock, which is committed. Without it
            # `nixos-26.05` is a branch resolved at lock-update time, and the toolchain would
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
              bind
              validationPython

              terraformPinned

              # The same hash-pinned 1.1.2 the CI shell uses. nixpkgs' 0.78.2 would parse none
              # of this repository's units — see the derivation above.
              terragruntPinned

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
                echo "  ERROR: terraform $have_tf does not match .terraform-version ($want_tf)."
                echo "           CI runs $want_tf. A newer local binary writes a state file the"
                echo "           CI version refuses to read, and the error reads like corruption."
                exit 1
              fi
              if [ "$have_tg" != "$want_tg" ] && [ "$want_tg" != "unknown" ]; then
                echo
                echo "  ERROR: terragrunt $have_tg does not match .terragrunt-version ($want_tg)."
                exit 1
              fi

              echo
              echo "  python3 scripts/plan-changed.py  plan only what this branch touches"
              echo "  docs/dependency-graph.md     apply order between stages"
            '';
          };
        in
        {
          inherit
            ciShell
            defaultShell
            pkgs
            terraformPinned
            terragruntPinned
            ;
        };
    in
    {
      packages = forAllSystems (system: {
        terraform = (perSystem system).terraformPinned;
        terragrunt = (perSystem system).terragruntPinned;
      });

      devShells = forAllSystems (system: {
        ci = (perSystem system).ciShell;
        default = (perSystem system).defaultShell;
      });

      checks = forAllSystems (system: {
        ci-shell = (perSystem system).ciShell;
        terraform = (perSystem system).terraformPinned;
        terragrunt = (perSystem system).terragruntPinned;
      });

      formatter = forAllSystems (system: (perSystem system).pkgs.nixfmt);
    };
}
