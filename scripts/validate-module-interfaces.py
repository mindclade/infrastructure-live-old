#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

#
"""Validate live Terragrunt module references against an exact monorepo Git checkout.

This script executes no monorepo code. It reads Git trees at each pinned module ref and checks
that every referenced module exists, each Terragrunt input name is declared by that module,
and every variable without a default is supplied by the unit or its shared environment
configuration. Terraform/Terragrunt planning remains the authoritative semantic validation,
but this preflight turns missing/scaffolded module interfaces into a small, explicit failure.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PREFIX = "infra/terraform/modules"
SEMVER_OR_SHA = re.compile(r"(?:v\d+\.\d+\.\d+|[0-9a-f]{40})")


def git(repo: Path, *args: str) -> str:
    cp = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
    if cp.returncode:
        raise RuntimeError(cp.stderr.strip() or "git command failed")
    return cp.stdout


def strip_strings_and_comments(line: str) -> str:
    line = line.split("#", 1)[0]
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', line)


def block(text: str, start_pattern: str) -> str | None:
    m = re.search(start_pattern, text, re.M)
    if not m:
        return None
    start = text.find("{", m.start())
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
    raise ValueError("unterminated HCL block")


def top_level_input_keys(text: str) -> set[str]:
    body = block(text, r"^\s*inputs\s*=\s*\{")
    if body is None:
        return set()
    keys: set[str] = set()
    depth = 0
    for line in body.splitlines():
        clean = strip_strings_and_comments(line)
        if depth == 0:
            m = re.match(r"\s*([A-Za-z0-9_-]+)\s*=", clean)
            if m:
                keys.add(m.group(1))
        depth += clean.count("{") - clean.count("}")
    return keys


def variable_contract(text: str) -> tuple[set[str], set[str]]:
    """Return all declared variables and the subset that have no default."""
    declared: set[str] = set()
    required: set[str] = set()
    for match in re.finditer(r'^\s*variable\s+"([^"]+)"\s*\{', text, re.M):
        name = match.group(1)
        body = block(text[match.start() :], r'^\s*variable\s+"[^"]+"\s*\{')
        if body is None:
            raise ValueError(f"variable {name} has no readable HCL block")
        declared.add(name)

        depth = 0
        has_default = False
        for line in body.splitlines():
            clean = strip_strings_and_comments(line)
            if depth == 0 and re.match(r"\s*default\s*=", clean):
                has_default = True
            depth += clean.count("{") - clean.count("}")
        if not has_default:
            required.add(name)
    return declared, required


def module_contract(text: str) -> tuple[str, str] | None:
    source = re.search(
        r'(?s)terraform\s*\{.*?source\s*=\s*"[^\"]*//([^?\"]+)\?ref=\$\{local\.module_version\}"',
        text,
    )
    version = re.search(r'module_version\s*=\s*"([^"]+)"', text)
    if not source:
        return None
    if not version:
        raise ValueError("module source has no literal local.module_version")
    ref = version.group(1)
    if not SEMVER_OR_SHA.fullmatch(ref):
        raise ValueError(
            f"module ref is not a protected full semver tag or commit SHA: {ref}"
        )
    return source.group(1), ref


def envcommon_path(unit_text: str) -> Path | None:
    m = re.search(r"_envcommon/([A-Za-z0-9_.-]+\.hcl)", unit_text)
    return ROOT / "_envcommon" / m.group(1) if m else None


def validate_candidate_version(repo: Path, candidate_version: str) -> None:
    """Require the candidate ref to match the monorepo's explicit planned contract."""
    policy_path = repo / "infra/terraform/governance/version.toml"
    if not policy_path.is_file():
        raise RuntimeError(f"candidate contract policy missing: {policy_path}")
    try:
        policy_text = policy_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"candidate contract policy is unreadable: {exc}") from exc

    policy: dict[str, str] = {}
    for key in ("contract_version", "status"):
        matches = re.findall(
            rf'^\s*{key}\s*=\s*"([^"\r\n]+)"\s*(?:#.*)?$', policy_text, re.M
        )
        if len(matches) != 1:
            raise RuntimeError(
                f"candidate contract policy must declare exactly one string {key}"
            )
        policy[key] = matches[0]

    expected = f"v{policy['contract_version']}"
    if policy["status"] != "planned" or candidate_version != expected:
        raise RuntimeError(
            "candidate ref must equal the monorepo's planned contract version "
            f"({expected}); found {candidate_version} with status {policy['status']!r}"
        )


def module_tf(
    repo: Path, ref: str, module: str, candidate_version: str | None = None
) -> str:
    if candidate_version is not None and ref == candidate_version:
        directory = repo / MODULE_PREFIX / module
        names = sorted(directory.glob("*.tf")) if directory.is_dir() else []
        if not names:
            raise RuntimeError(
                f"planned {ref}:{MODULE_PREFIX}/{module} does not contain Terraform source"
            )
        return "\n".join(path.read_text(encoding="utf-8") for path in names)

    prefix = f"{MODULE_PREFIX}/{module}/"
    names = [
        n
        for n in git(
            repo, "ls-tree", "-r", "--name-only", ref, "--", prefix
        ).splitlines()
        if n.endswith(".tf")
    ]
    if not names:
        raise RuntimeError(
            f"{ref}:{MODULE_PREFIX}/{module} does not contain Terraform source"
        )
    return "\n".join(git(repo, "show", f"{ref}:{name}") for name in names)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--monorepo", required=True, type=Path)
    ap.add_argument(
        "--candidate-version",
        help=(
            "validate only callers pinned to this planned version against the monorepo "
            "worktree; this source-review mode never proves an immutable release"
        ),
    )
    args = ap.parse_args()
    repo = args.monorepo.resolve()
    if not (repo / ".git").exists():
        print(f"ERROR: --monorepo must be a Git checkout: {repo}", file=sys.stderr)
        return 2
    if args.candidate_version is not None:
        if not re.fullmatch(r"v\d+\.\d+\.\d+", args.candidate_version):
            print("ERROR: --candidate-version must be a full vMAJOR.MINOR.PATCH tag", file=sys.stderr)
            return 2
        try:
            validate_candidate_version(repo, args.candidate_version)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    errors: list[str] = []
    checked = 0
    cache: dict[tuple[str, str], tuple[set[str], set[str]]] = {}

    for config in sorted(ROOT.rglob("terragrunt.hcl")):
        if any(p in {".terragrunt-cache", ".terraform"} for p in config.parts):
            continue
        unit_text = config.read_text(encoding="utf-8")
        contract_text = unit_text
        common = envcommon_path(unit_text)
        if module_contract(contract_text) is None and common:
            if not common.is_file():
                errors.append(
                    f"{config.relative_to(ROOT)}: included envcommon file missing: {common.relative_to(ROOT)}"
                )
                continue
            contract_text = common.read_text(encoding="utf-8")
        try:
            contract = module_contract(contract_text)
        except ValueError as exc:
            errors.append(f"{config.relative_to(ROOT)}: {exc}")
            continue
        if contract is None:
            # A small number of local Terraform units intentionally use ./module or generated source.
            continue
        module, ref = contract
        inputs = top_level_input_keys(contract_text) | top_level_input_keys(unit_text)
        key = (ref, module)
        try:
            contract = cache.get(key)
            if contract is None:
                tf = module_tf(repo, ref, module, args.candidate_version)
                variables, required = variable_contract(tf)
                if not variables:
                    raise RuntimeError(
                        f"{ref}:{MODULE_PREFIX}/{module} declares no Terraform variables (scaffold/incomplete module)"
                    )
                cache[key] = (variables, required)
            else:
                variables, required = contract
            extra = sorted(inputs - variables)
            if extra:
                errors.append(
                    f"{config.relative_to(ROOT)} -> {module}@{ref}: undeclared input(s): {', '.join(extra)}"
                )
            missing = sorted(required - inputs)
            if missing:
                errors.append(
                    f"{config.relative_to(ROOT)} -> {module}@{ref}: missing required input(s): {', '.join(missing)}"
                )
            checked += 1
        except RuntimeError as exc:
            errors.append(f"{config.relative_to(ROOT)} -> {module}@{ref}: {exc}")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print(
            f"module-interface preflight failed: {len(errors)} violation(s), {checked} unit(s) checked",
            file=sys.stderr,
        )
        return 1
    suffix = (
        f"; {args.candidate_version} was read from the planned worktree and is not a released ref"
        if args.candidate_version is not None
        else ""
    )
    print(
        f"module-interface preflight passed: {checked} unit(s), "
        f"{len(cache)} module/ref pair(s){suffix}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
