#!/usr/bin/env python3
"""Select the minimum infrastructure-live apply scopes for a merged commit.

The script deliberately ignores documentation/tooling-only changes. A manual dispatch must
name a scope, and an optional unit is validated against that scope before a privileged job is
created.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCOPE_PREFIXES: dict[str, tuple[str, ...]] = {
    "foundation": ("1-org/", "3-networks/shared/", "5-workloads/shared/"),
    "development": (
        "2-environments/development/",
        "3-networks/development/",
        "4-projects/development/",
        "5-workloads/development/",
    ),
    "staging": (
        "2-environments/staging/",
        "3-networks/staging/",
        "4-projects/staging/",
        "5-workloads/staging/",
    ),
    "production": (
        "2-environments/production/",
        "3-networks/production/",
        "4-projects/production/",
        "5-workloads/production/",
    ),
    "partners": ("4-projects/partners/", "5-workloads/partners/"),
}
GLOBAL_FILES = {"account.hcl", "root.hcl"}
GLOBAL_PREFIXES = ("_envcommon/",)
FOUNDATION_SPECIAL_PREFIXES = (
    "5-workloads/development/vpc-sc-perimeter/",
    "5-workloads/staging/vpc-sc-perimeter/",
    "5-workloads/production/vpc-sc-perimeter/",
)
ENVIRONMENT = {
    "foundation": "production",
    "development": "development",
    "staging": "staging",
    "production": "production",
    "partners": "production",
}
ORDER = tuple(SCOPE_PREFIXES)


def fail(message: str) -> "NoReturn":
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def normalize_unit(raw: str) -> str:
    value = raw.strip().rstrip("/")
    if not value:
        return ""
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        fail("unit must be a normalized repository-relative path")
    if "\\" in value:
        fail("unit must use POSIX separators")
    candidate = (ROOT / value).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        fail("unit escapes the repository root")
    if not (candidate / "terragrunt.hcl").is_file():
        fail(f"{value!r} is not a Terragrunt unit")
    return value


def scope_for_path(path: str) -> set[str]:
    path = path.removeprefix("./")
    if path in GLOBAL_FILES or path.startswith(GLOBAL_PREFIXES):
        return set(ORDER)
    if path.startswith(FOUNDATION_SPECIAL_PREFIXES):
        return {"foundation"}
    return {
        scope
        for scope, prefixes in SCOPE_PREFIXES.items()
        if path.startswith(prefixes)
    }


def scope_has_live_units(scope: str) -> bool:
    """Return whether a scope contains at least one executable Terragrunt unit."""
    for prefix in SCOPE_PREFIXES[scope]:
        root = ROOT / prefix.rstrip("/")
        if root.is_file() and root.name == "terragrunt.hcl":
            return True
        if root.is_dir() and any(root.rglob("terragrunt.hcl")):
            return True
    return scope == "foundation" and any(
        (ROOT / prefix.rstrip("/") / "terragrunt.hcl").is_file()
        for prefix in FOUNDATION_SPECIAL_PREFIXES
    )


def changed_paths(before: str, after: str) -> list[str]:
    if not before or set(before) == {"0"}:
        command = ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", after]
    else:
        command = ["git", "diff", "--name-only", before, after]
    result = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", default="")
    parser.add_argument("--after", default="HEAD")
    parser.add_argument("--manual-scope", choices=ORDER)
    parser.add_argument("--unit", default="")
    args = parser.parse_args()

    unit = normalize_unit(args.unit)
    if args.manual_scope:
        if not scope_has_live_units(args.manual_scope):
            fail(f"scope {args.manual_scope!r} contains no live Terragrunt units")
        scopes = {args.manual_scope}
        if unit and args.manual_scope not in scope_for_path(f"{unit}/"):
            fail(f"unit {unit!r} does not belong to scope {args.manual_scope!r}")
    else:
        if unit:
            fail("--unit is valid only with --manual-scope")
        scopes: set[str] = set()
        for path in changed_paths(args.before, args.after):
            scopes.update(scope_for_path(path))

    matrix = {
        "include": [
            {"scope": scope, "environment": ENVIRONMENT[scope], "unit": unit}
            for scope in ORDER
            if scope in scopes and scope_has_live_units(scope)
        ]
    }
    print(json.dumps(matrix, separators=(",", ":")))


if __name__ == "__main__":
    main()
