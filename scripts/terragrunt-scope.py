#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Create and apply an exact checksummed Terragrunt plan bundle for one scope."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCOPES = {
    "foundation": [
        "1-org",
        "3-networks/shared",
        "5-workloads/shared",
        "5-workloads/development/vpc-sc-perimeter",
        "5-workloads/staging/vpc-sc-perimeter",
        "5-workloads/production/vpc-sc-perimeter",
    ],
    "development": [
        "2-environments/development",
        "3-networks/development",
        "4-projects/development",
        "5-workloads/development",
    ],
    "staging": [
        "2-environments/staging",
        "3-networks/staging",
        "4-projects/staging",
        "5-workloads/staging",
    ],
    "production": [
        "2-environments/production",
        "3-networks/production",
        "4-projects/production",
        "5-workloads/production",
    ],
    "partners": ["4-projects/partners", "5-workloads/partners"],
}
REQUIRED_BUNDLE_FILES = {
    "ACCOUNT_RUNTIME.json",
    "PLAN_CLASSIFICATION.json",
    "PLAN_SHA256SUMS",
    "RUN_CONTEXT.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("scope", choices=tuple(SCOPES))
    parser.add_argument("plan_dir", type=Path)
    parser.add_argument("unit", nargs="?", default="")
    return parser.parse_args()


def within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validated_plan_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    anchors = [Path(tempfile.gettempdir()).resolve(), (ROOT / ".plans").resolve()]
    runner_temp = os.environ.get("RUNNER_TEMP")
    if runner_temp:
        anchors.insert(0, Path(runner_temp).resolve())
    if not any(resolved != anchor and within(resolved, anchor) for anchor in anchors):
        allowed = ", ".join(str(anchor / "<bundle>") for anchor in anchors)
        raise ValueError(
            f"unsafe plan directory {resolved}; expected a child of: {allowed}"
        )
    if resolved in {ROOT, ROOT.parent, Path(resolved.anchor)}:
        raise ValueError(f"refusing broad plan directory: {resolved}")
    return resolved


def validate_unit(scope: str, unit: str, roots: list[str]) -> str:
    candidate = Path(unit)
    if not unit or candidate.is_absolute() or ".." in candidate.parts or "\\" in unit:
        raise ValueError(f"invalid unit path: {unit}")
    normalized = candidate.as_posix()
    unit_path = (ROOT / candidate).resolve()
    if not within(unit_path, ROOT) or not (unit_path / "terragrunt.hcl").is_file():
        raise ValueError(f"no terragrunt.hcl at {unit}")
    special = (
        normalized.startswith("5-workloads/") and "/vpc-sc-perimeter" in normalized
    )
    if special and scope != "foundation":
        raise ValueError("VPC Service Controls units are foundation-owned")
    if not any(
        normalized == root or normalized.startswith(f"{root}/") for root in roots
    ):
        raise ValueError(f"unit {unit} is outside scope {scope}")
    return normalized


def runtime_account() -> bytes:
    result = subprocess.run(
        [sys.executable, "scripts/validate-account.py", "--runtime", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    json.loads(result.stdout)
    return result.stdout


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def repository_identity() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "local")


def run_root(mode: str, scope: str, root: str, bundle: Path) -> None:
    root_path = ROOT / root
    if not root_path.is_dir() or not any(root_path.rglob("terragrunt.hcl")):
        return
    output = bundle / root.replace("/", "__")
    plans = output / "plans"
    rendered_json = output / "json"
    plans.mkdir(parents=True, exist_ok=True)
    rendered_json.mkdir(parents=True, exist_ok=True)
    arguments = [
        "nix",
        "develop",
        ".#ci",
        "--command",
        "terragrunt",
        "run",
        "--all",
        "--provider-cache",
        "--non-interactive",
        "--queue-exclude-external",
        "--working-dir",
        root,
        "--out-dir",
        str(plans),
    ]
    if mode == "plan":
        arguments.extend(["--json-out-dir", str(rendered_json)])
    if root in {
        "5-workloads/development",
        "5-workloads/staging",
        "5-workloads/production",
    }:
        arguments.extend(["--filter", "!./vpc-sc-perimeter/**"])
    arguments.extend(["--", mode, "-input=false", "-no-color", "-lock-timeout=20m"])
    print(f"::group::{mode} {scope} {root}")
    try:
        subprocess.run(arguments, cwd=ROOT, check=True)
    finally:
        print("::endgroup::")


def bundle_context(scope: str, unit: str) -> dict[str, str]:
    return {
        "schema_version": "1.0.0",
        "repository": repository_identity(),
        "commit_sha": git_commit(),
        "scope": scope,
        "unit": unit,
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def checksum_entries(bundle: Path) -> list[tuple[str, str]]:
    entries = []
    for path in sorted(
        candidate for candidate in bundle.rglob("*") if candidate.is_file()
    ):
        relative = path.relative_to(bundle).as_posix()
        if relative == "PLAN_SHA256SUMS":
            continue
        if "\n" in relative:
            raise ValueError(f"bundle path contains a newline: {relative!r}")
        entries.append((hashlib.sha256(path.read_bytes()).hexdigest(), relative))
    return entries


def write_checksums(bundle: Path) -> None:
    entries = checksum_entries(bundle)
    if not entries:
        raise ValueError("no saved plans were generated")
    content = "".join(f"{digest}  {name}\n" for digest, name in entries)
    (bundle / "PLAN_SHA256SUMS").write_text(content, encoding="utf-8")


def verify_checksums(bundle: Path) -> None:
    expected: list[tuple[str, str]] = []
    for line in (bundle / "PLAN_SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if len(line) < 67 or line[64:66] != "  ":
            raise ValueError("malformed PLAN_SHA256SUMS entry")
        expected.append((line[:64], line[66:]))
    actual = checksum_entries(bundle)
    if expected != actual:
        raise ValueError(
            "plan bundle checksum manifest does not match its exact contents"
        )


def verify_context(bundle: Path, scope: str, unit: str) -> None:
    stored_account = (bundle / "ACCOUNT_RUNTIME.json").read_bytes()
    if json.loads(stored_account) != json.loads(runtime_account()):
        raise ValueError(
            "bootstrap-derived account inputs changed after the saved plan"
        )
    context = json.loads((bundle / "RUN_CONTEXT.json").read_text(encoding="utf-8"))
    expected = bundle_context(scope, unit)
    if set(context) != set(expected) or context != expected:
        raise ValueError(
            f"plan run context mismatch: expected {expected}, found {context}"
        )


def create_plan(scope: str, unit: str, roots: list[str], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        for root in roots:
            run_root("plan", scope, root, staging)
        (staging / "ACCOUNT_RUNTIME.json").write_bytes(runtime_account())
        write_json(staging / "RUN_CONTEXT.json", bundle_context(scope, unit))
        subprocess.run(
            [
                sys.executable,
                "scripts/classify-plans.py",
                str(staging),
                "--output",
                str(staging / "PLAN_CLASSIFICATION.json"),
            ],
            cwd=ROOT,
            check=True,
        )
        write_checksums(staging)
        if destination.exists():
            shutil.rmtree(destination)
        staging.replace(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def apply_plan(scope: str, unit: str, roots: list[str], bundle: Path) -> None:
    if not bundle.is_dir():
        raise ValueError(f"saved plan bundle does not exist: {bundle}")
    missing = sorted(
        name for name in REQUIRED_BUNDLE_FILES if not (bundle / name).is_file()
    )
    if missing:
        raise ValueError(f"saved plan bundle is missing: {', '.join(missing)}")
    verify_checksums(bundle)
    verify_context(bundle, scope, unit)
    for root in roots:
        run_root("apply", scope, root, bundle)


def main() -> int:
    args = parse_args()
    try:
        plan_dir = validated_plan_path(args.plan_dir)
        roots = list(SCOPES[args.scope])
        unit = validate_unit(args.scope, args.unit, roots) if args.unit else ""
        if unit:
            roots = [unit]
        os.environ.update({"TG_STRICT_MODE": "true", "TG_NON_INTERACTIVE": "true"})
        if args.mode == "plan":
            create_plan(args.scope, unit, roots, plan_dir)
        else:
            apply_plan(args.scope, unit, roots, plan_dir)
        return 0
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
