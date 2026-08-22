#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Validate live GKE identity bindings against immutable Kubernetes source.

Exact mode reads the monorepo at the semantic module ref selected by the live
identity unit. Candidate mode reads only the matching planned worktree and does
not prove that the ref has been published.
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
SEMVER = re.compile(r"v\d+\.\d+\.\d+")
IDENTITIES = {
    "preprocessing": {
        "account_id": "preprocessing",
        "namespace": "mindclade-batch-cpu",
        "ksa_name": "mindclade-batch-cpu",
    },
    "training_h100": {
        "account_id": "training-h100",
        "namespace": "mindclade-training-h100",
        "ksa_name": "mindclade-training-h100",
    },
    "training_b200": {
        "account_id": "training-b200",
        "namespace": "mindclade-training-b200",
        "ksa_name": "mindclade-training-b200",
    },
    "holdout_evaluator": {
        "account_id": "holdout-evaluator",
        "namespace": "mindclade-evaluation",
        "ksa_name": "mindclade-holdout-evaluator",
    },
}
DENIED_IDENTITIES = ("preprocessing", "training_h100", "training_b200")


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


def map_entry(text: str, key: str) -> str | None:
    match = re.search(
        rf"(?ms)^\s{{4}}{re.escape(key)}\s*=\s*\{{(?P<body>.*?)^\s{{4}}\}}",
        text,
    )
    return match.group("body") if match else None


def live_contract() -> tuple[str, list[str]]:
    errors: list[str] = []
    common_path = ROOT / "_envcommon/workload-identities.hcl"
    common = common_path.read_text(encoding="utf-8")
    refs = re.findall(r'^\s*module_version\s*=\s*"([^"\r\n]+)"', common, re.M)
    if len(refs) != 1 or not SEMVER.fullmatch(refs[0]):
        errors.append(
            "_envcommon/workload-identities.hcl must select one full semantic module ref"
        )
        ref = refs[0] if refs else ""
    else:
        ref = refs[0]

    if common.count("project_roles = []") != len(IDENTITIES):
        errors.append("workload identities must start with zero project-wide roles")
    for key, contract in IDENTITIES.items():
        block = map_entry(common, key)
        if block is None:
            errors.append(f"shared workload identity omits {key}")
            continue
        required = f'account_id    = "{contract["account_id"]}"'
        if required not in block:
            errors.append(f"shared workload identity {key} omits {required!r}")

    for environment in ENVIRONMENTS:
        unit_path = (
            ROOT / f"5-workloads/{environment}/workload-identities/terragrunt.hcl"
        )
        unit = unit_path.read_text(encoding="utf-8")
        relative = unit_path.relative_to(ROOT)
        if unit.count("service_account_key =") != len(IDENTITIES):
            errors.append(f"{relative} must declare exactly {len(IDENTITIES)} KSA bindings")
        for key, contract in IDENTITIES.items():
            block = map_entry(unit, key)
            if block is None:
                errors.append(f"{relative} omits binding {key}")
                continue
            for required in (
                f'service_account_key = "{key}"',
                f'namespace           = "{contract["namespace"]}"',
                f'ksa_name            = "{contract["ksa_name"]}"',
                'gke_project_id      = dependency.shared.outputs.project_ids["platform"]',
            ):
                if required not in block:
                    errors.append(f"{relative} binding {key} omits {required!r}")

        holdout_path = (
            ROOT / f"5-workloads/{environment}/storage/gcs-holdout/terragrunt.hcl"
        )
        holdout = holdout_path.read_text(encoding="utf-8")
        holdout_relative = holdout_path.relative_to(ROOT)
        if 'dependency "workload_identities"' not in holdout:
            errors.append(f"{holdout_relative} lacks the workload identity dependency")
        for key in DENIED_IDENTITIES:
            reference = (
                'dependency.workload_identities.outputs.service_accounts['
                f'"{key}"].email'
            )
            if holdout.count(reference) != 1:
                errors.append(
                    f"{holdout_relative} must deny exactly one typed {key} principal"
                )
        evaluator_reference = (
            'dependency.workload_identities.outputs.service_accounts['
            '"holdout_evaluator"].email'
        )
        if holdout.count(evaluator_reference) != 1:
            errors.append(
                f"{holdout_relative} must grant exactly one typed evaluator principal"
            )
        for required in (
            'bucket_iam_members = {',
            'bucket_key = "holdout"',
            'role       = "roles/storage.objectViewer"',
            f'member     = "serviceAccount:${{{evaluator_reference}}}"',
        ):
            if holdout.count(required) != 1:
                errors.append(
                    f"{holdout_relative} evaluator grant omits exact {required!r}"
                )
        for stale in ("serviceAccounts/training@", "serviceAccounts/preprocessing@"):
            if stale in holdout:
                errors.append(f"{holdout_relative} retains inferred principal {stale!r}")
    return ref, errors


def kubernetes_contract_errors(
    environment: str, read: Callable[[str], str]
) -> list[str]:
    errors: list[str] = []
    try:
        service_accounts = read("infra/kubernetes/base/service-accounts.yaml")
        overlay = read(
            f"infra/kubernetes/overlays/{environment}/kustomization.yaml"
        )
    except RuntimeError as exc:
        return [str(exc)]

    research_project = f"mc-{environment}-research"
    for key, contract in IDENTITIES.items():
        resource = (
            f'name: {contract["ksa_name"]}\n'
            f'  namespace: {contract["namespace"]}'
        )
        if service_accounts.count(resource) != 1:
            errors.append(
                f"base service-account inventory must contain exactly one "
                f"{contract['namespace']}/{contract['ksa_name']}"
            )
        email = f"{contract['account_id']}@{research_project}.iam.gserviceaccount.com"
        if overlay.count(email) != 1:
            errors.append(
                f"{environment} overlay must bind exactly one {key} KSA to {email}"
            )
    if overlay.count("no-api-token-workload-identity") != len(IDENTITIES):
        errors.append(
            f"{environment} overlay must mark exactly {len(IDENTITIES)} keyless identities"
        )
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

    ref, errors = live_contract()
    if args.candidate_version is not None:
        if not SEMVER.fullmatch(args.candidate_version):
            errors.append("--candidate-version must be a full vMAJOR.MINOR.PATCH tag")
        elif args.candidate_version != ref:
            errors.append(
                f"candidate version {args.candidate_version} does not match live identity ref {ref}"
            )
        else:
            try:
                candidate_policy(repo, args.candidate_version)
            except RuntimeError as exc:
                errors.append(str(exc))

    def read(path: str) -> str:
        if args.candidate_version == ref:
            try:
                return (repo / path).read_text(encoding="utf-8")
            except OSError as exc:
                raise RuntimeError(f"{path}: {exc}") from exc
        try:
            return git(repo, "show", f"{ref}:{path}")
        except RuntimeError as exc:
            raise RuntimeError(f"{ref}:{path}: {exc}") from exc

    if ref:
        for environment in ENVIRONMENTS:
            errors.extend(kubernetes_contract_errors(environment, read))
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
        "cross-repository GKE workload identity contract passed: "
        f"{len(ENVIRONMENTS)} environments, {len(IDENTITIES)} identities, {mode}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
