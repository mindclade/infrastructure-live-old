#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Validate the live GPU estate against the monorepo Kubernetes capacity contract.

The exact mode reads Kubernetes source from the immutable Git ref selected by the
live GPU node-pool module. Candidate mode reads only that planned ref from the
review worktree and therefore cannot prove release provenance.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = ("development", "staging", "production")
POOLS = ("gpu-a3", "gpu-a4")
PROFILE_CODES = {
    "gke-h100-a3-megagpu-8g": "h100",
    "gke-h200-a3-ultragpu-8g": "h200",
    "gke-b200-a4-highgpu-8g": "b200",
}
CANONICAL_POOL_PROFILES = {
    "gpu-a3": "gke-h100-a3-megagpu-8g",
    # gpu-a4 is a retained Terragrunt state address, not the selected machine series.
    "gpu-a4": "gke-b200-a4-highgpu-8g",
}
SEMVER = re.compile(r"v\d+\.\d+\.\d+")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], text=True, capture_output=True
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def candidate_policy(repo: Path, candidate: str) -> None:
    path = repo / "infra/terraform/governance/version.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"candidate contract policy is unreadable: {exc}") from exc
    fields: dict[str, str] = {}
    for name in ("contract_version", "status"):
        values = re.findall(
            rf'^\s*{name}\s*=\s*"([^"\r\n]+)"\s*(?:#.*)?$', text, re.M
        )
        if len(values) != 1:
            raise RuntimeError(
                f"candidate contract policy must declare exactly one string {name}"
            )
        fields[name] = values[0]
    expected = f"v{fields['contract_version']}"
    if fields["status"] != "planned" or candidate != expected:
        raise RuntimeError(
            "candidate ref must equal the monorepo's planned contract version "
            f"({expected}); found {candidate} with status {fields['status']!r}"
        )


def live_contract() -> tuple[str, dict[str, str], list[str]]:
    errors: list[str] = []
    common = (ROOT / "_envcommon/gpu-nodepool.hcl").read_text(encoding="utf-8")
    refs = re.findall(r'^\s*module_version\s*=\s*"([^"\r\n]+)"', common, re.M)
    if len(refs) != 1 or not SEMVER.fullmatch(refs[0]):
        errors.append("_envcommon/gpu-nodepool.hcl must select one full semantic module ref")
        ref = refs[0] if refs else ""
    else:
        ref = refs[0]

    by_environment: dict[str, dict[str, str]] = {}
    for environment in ENVIRONMENTS:
        by_environment[environment] = {}
        for pool in POOLS:
            path = ROOT / f"5-workloads/{environment}/nodepools/{pool}/terragrunt.hcl"
            text = path.read_text(encoding="utf-8")
            profiles = re.findall(r'^\s*profile\s*=\s*"([^"\r\n]+)"', text, re.M)
            if len(profiles) != 1:
                errors.append(
                    f"{path.relative_to(ROOT)} must select exactly one literal GPU profile"
                )
                continue
            profile = profiles[0]
            if profile not in PROFILE_CODES:
                errors.append(f"{path.relative_to(ROOT)} selects unsupported profile {profile}")
            by_environment[environment][pool] = profile

    baseline = by_environment[ENVIRONMENTS[0]]
    for environment in ENVIRONMENTS[1:]:
        if by_environment[environment] != baseline:
            errors.append(
                f"{environment} GPU pool/profile mapping differs from development: "
                f"{by_environment[environment]} != {baseline}"
            )
    if len(set(baseline.values())) != len(POOLS):
        errors.append("live GPU pools must select distinct accelerator profiles")
    if baseline != CANONICAL_POOL_PROFILES:
        errors.append(
            "live GPU pool/profile mapping differs from the approved H100 A3 Mega + "
            f"B200 A4 contract: {baseline} != {CANONICAL_POOL_PROFILES}"
        )
    return ref, baseline, errors


def contract_errors(profiles: set[str], read: Callable[[str], str]) -> list[str]:
    errors: list[str] = []
    unknown = sorted(profiles - set(PROFILE_CODES))
    if unknown:
        return [f"unsupported live GPU profile(s): {', '.join(unknown)}"]

    static_paths = {
        "namespaces": "infra/kubernetes/base/namespace.yaml",
        "gpu": "infra/kubernetes/platform/gpu/resources.yaml",
        "kueue": "infra/kubernetes/platform/kueue/resources.yaml",
        "qualification": "infra/kubernetes/platform/qualification/kustomization.yaml",
    }
    documents: dict[str, str] = {}
    for name, path in static_paths.items():
        try:
            documents[name] = read(path)
        except RuntimeError as exc:
            errors.append(f"{path}: {exc}")
    if errors:
        return errors

    kueue_profiles = set(
        re.findall(
            r"mindclade\.dev/gpu-profile:\s*(gke-[a-z0-9-]+)",
            documents["kueue"],
        )
    )
    gpu_profiles = set(
        re.findall(
            r"^\s*[a-z0-9]+Profile:\s*(gke-[a-z0-9-]+)\s*$",
            documents["gpu"],
            re.M,
        )
    )
    if kueue_profiles != profiles:
        errors.append(
            "Kueue ResourceFlavor profiles differ from live Terraform profiles: "
            f"{sorted(kueue_profiles)} != {sorted(profiles)}"
        )
    if gpu_profiles != profiles:
        errors.append(
            "GPU platform profiles differ from live Terraform profiles: "
            f"{sorted(gpu_profiles)} != {sorted(profiles)}"
        )

    expected_domains = {f"mindclade-training-{PROFILE_CODES[p]}" for p in profiles}
    observed_domains = set(
        re.findall(r"^\s*name:\s*(mindclade-training-(?:h100|h200|b200))\s*$", documents["namespaces"], re.M)
    )
    if observed_domains != expected_domains:
        errors.append(
            "Kubernetes GPU capacity namespaces differ from live profiles: "
            f"{sorted(observed_domains)} != {sorted(expected_domains)}"
        )

    for profile in sorted(profiles):
        code = PROFILE_CODES[profile]
        flavor = f"mindclade-{code}"
        domain = f"mindclade-training-{code}"
        for required in (
            f"name: {flavor}",
            f"mindclade.dev/gpu-profile: {profile}",
            f"name: {domain}",
            f"namespace: {domain}",
        ):
            if required not in documents["kueue"]:
                errors.append(f"Kueue contract for {profile} omits {required!r}")
        if f"{code}Profile: {profile}" not in documents["gpu"]:
            errors.append(f"GPU platform contract for {profile} is missing")
        if f"- {code}-job.json" not in documents["qualification"]:
            errors.append(f"qualification inventory omits {code}-job.json")

        dynamic_paths = {
            "job": f"infra/kubernetes/platform/qualification/{code}-job.json",
            "overlay": (
                "infra/kubernetes/workloads/training/overlays/"
                f"{code}/kustomization.yaml"
            ),
        }
        for kind, path in dynamic_paths.items():
            try:
                text = read(path)
            except (KeyError, RuntimeError) as exc:
                errors.append(f"{path}: {exc}")
                continue
            required_values = (
                (f'"mindclade.dev/gpu-profile": "{profile}"', f'"{code}"')
                if kind == "job"
                else (
                    f"namespace: {domain}",
                    f"value: {profile}",
                    f"value: {domain}",
                )
            )
            for required in required_values:
                if required not in text:
                    errors.append(f"{path} omits {required!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--monorepo", required=True, type=Path)
    parser.add_argument(
        "--candidate-version",
        help="read the matching planned ref from the worktree; never proves a release",
    )
    args = parser.parse_args()
    repo = args.monorepo.resolve()
    if not (repo / ".git").exists():
        print(f"ERROR: --monorepo must be a Git checkout: {repo}", file=sys.stderr)
        return 2

    ref, pool_profiles, errors = live_contract()
    if args.candidate_version is not None:
        if not SEMVER.fullmatch(args.candidate_version):
            errors.append("--candidate-version must be a full vMAJOR.MINOR.PATCH tag")
        elif args.candidate_version != ref:
            errors.append(
                f"candidate version {args.candidate_version} does not match live GPU ref {ref}"
            )
        else:
            try:
                candidate_policy(repo, args.candidate_version)
            except RuntimeError as exc:
                errors.append(str(exc))

    def read(path: str) -> str:
        if args.candidate_version == ref:
            candidate_path = repo / path
            try:
                return candidate_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise RuntimeError(str(exc)) from exc
        try:
            return git(repo, "show", f"{ref}:{path}")
        except RuntimeError as exc:
            raise RuntimeError(f"{ref}: {exc}") from exc

    if ref and pool_profiles:
        errors.extend(contract_errors(set(pool_profiles.values()), read))
    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    mode = (
        f"planned worktree {ref}; not release provenance"
        if args.candidate_version is not None
        else f"immutable Git ref {ref}"
    )
    print(
        "cross-repository GPU/Kueue capacity contract passed: "
        f"{len(pool_profiles)} pools, {len(set(pool_profiles.values()))} profiles, {mode}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
