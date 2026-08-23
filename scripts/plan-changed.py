#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Plan changed Terragrunt units and their complete dependent closure."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


DEPENDENCY_PATTERN = re.compile(r'config_path\s*=\s*"([^"]+)"')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_ref", nargs="?", default="origin/main")
    parser.add_argument("--impact-output", type=Path)
    return parser.parse_args()


def git_root() -> Path:
    output = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    return Path(output.strip()).resolve()


def terragrunt_units(root: Path) -> list[Path]:
    return sorted(
        path.parent.relative_to(root)
        for path in root.rglob("terragrunt.hcl")
        if ".terragrunt-cache" not in path.parts
    )


def directly_changed_units(root: Path, base: str, all_units: list[Path]) -> set[Path]:
    output = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    changed = [Path(line) for line in output.splitlines() if line]
    if not changed:
        return set()
    if any(
        path == Path("root.hcl")
        or path == Path("account.hcl")
        or path.parts[:1] == ("_envcommon",)
        for path in changed
    ):
        print("Shared configuration changed — planning every unit.")
        return set(all_units)
    units = set()
    for path in changed:
        if path.suffix != ".hcl" or len(path.parts) < 2:
            continue
        candidate = path.parent
        if (root / candidate / "terragrunt.hcl").is_file():
            units.add(candidate)
    return units


def dependency_map(root: Path, units: list[Path]) -> dict[Path, set[Path]]:
    dependencies: dict[Path, set[Path]] = {}
    for unit in units:
        text = (root / unit / "terragrunt.hcl").read_text(encoding="utf-8")
        edges: set[Path] = set()
        for configured in DEPENDENCY_PATTERN.findall(text):
            candidate = (root / unit / configured).resolve()
            try:
                edges.add(candidate.relative_to(root))
            except ValueError:
                print(
                    f'::warning::{unit} declares config_path "{configured}" outside the repository',
                    file=sys.stderr,
                )
                continue
            if not candidate.is_dir():
                print(
                    f'::warning::{unit} declares config_path "{configured}", which is not a directory',
                    file=sys.stderr,
                )
        dependencies[unit] = edges
    return dependencies


def dependent_closure(selected: set[Path], dependencies: dict[Path, set[Path]]) -> int:
    rounds = 0
    while True:
        rounds += 1
        additions = {
            unit
            for unit, edges in dependencies.items()
            if unit not in selected and edges & selected
        }
        for unit in sorted(additions):
            dependency = sorted(dependencies[unit] & selected)[0]
            print(f"  + {unit} (depends on {dependency})")
        if not additions:
            return rounds
        selected.update(additions)
        if rounds > 50:
            raise RuntimeError("dependent resolution did not converge after 50 rounds")


def scope_for(unit: Path) -> str:
    parts = unit.parts
    for environment in ("development", "staging", "production", "partners"):
        if environment in parts:
            return environment
    return "foundation"


def write_impact(
    path: Path,
    base_ref: str,
    direct: set[Path],
    selected: set[Path],
) -> None:
    dependent = selected - direct
    scopes = sorted({scope_for(unit) for unit in selected})
    unit_strings = [item.as_posix() for item in sorted(selected)]
    result = {
        "schemaVersion": 1,
        "baseRef": base_ref,
        "directUnits": [item.as_posix() for item in sorted(direct)],
        "dependentUnits": [item.as_posix() for item in sorted(dependent)],
        "plannedUnits": unit_strings,
        "scopes": scopes,
        "summary": {
            "directUnitCount": len(direct),
            "dependentUnitCount": len(dependent),
            "plannedUnitCount": len(selected),
        },
        "reviewFlags": {
            "foundation": "foundation" in scopes,
            "production": "production" in scopes,
            "network": any(value.startswith("3-networks/") for value in unit_strings),
            "identityOrPolicy": any(
                value.startswith("1-org/")
                or "workload-identit" in value
                or "binary-authorization" in value
                or "vpc-sc-perimeter" in value
                for value in unit_strings
            ),
            "requiresConnectedPlanReview": bool(selected),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def plan(root: Path, unit: Path) -> int:
    print(f"\n════════ {unit} ════════")
    result = subprocess.run(
        [
            "terragrunt",
            "run",
            "--provider-cache",
            "--non-interactive",
            "--",
            "plan",
            "-input=false",
            "-no-color",
            "-lock-timeout=20m",
        ],
        cwd=root / unit,
        check=False,
    )
    if result.returncode:
        print(f"::error::plan failed in {unit}", file=sys.stderr)
    return result.returncode


def main() -> int:
    args = parse_args()
    try:
        root = git_root()
        units = terragrunt_units(root)
        selected = directly_changed_units(root, args.base_ref, units)
        direct = set(selected)
        if not selected:
            if args.impact_output:
                write_impact(args.impact_output, args.base_ref, direct, selected)
            print(f"No Terragrunt units affected against {args.base_ref}.")
            return 0
        rounds = dependent_closure(selected, dependency_map(root, units))
        if args.impact_output:
            write_impact(args.impact_output, args.base_ref, direct, selected)
        print(f"\nPlanning {len(selected)} unit(s) (converged in {rounds} round(s)):")
        for unit in sorted(selected):
            print(f"  {unit}")
        return 1 if any(plan(root, unit) for unit in sorted(selected)) else 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
