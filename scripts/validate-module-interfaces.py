#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

#
"""Validate live Terragrunt module references against an exact monorepo Git checkout.

This script executes no monorepo code. It reads Git trees at each pinned module ref and checks
that every referenced module exists and that each Terragrunt input name is declared by that
module. Terraform/Terragrunt planning remains the authoritative semantic validation, but this
preflight turns missing/scaffolded module interfaces into a small, explicit failure.
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


def module_tf(repo: Path, ref: str, module: str) -> str:
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
    args = ap.parse_args()
    repo = args.monorepo.resolve()
    if not (repo / ".git").exists():
        print(f"ERROR: --monorepo must be a Git checkout: {repo}", file=sys.stderr)
        return 2

    errors: list[str] = []
    checked = 0
    cache: dict[tuple[str, str], set[str]] = {}

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
            variables = cache.get(key)
            if variables is None:
                tf = module_tf(repo, ref, module)
                variables = set(re.findall(r'variable\s+"([^"]+)"', tf))
                if not variables:
                    raise RuntimeError(
                        f"{ref}:{MODULE_PREFIX}/{module} declares no Terraform variables (scaffold/incomplete module)"
                    )
                cache[key] = variables
            extra = sorted(inputs - variables)
            if extra:
                errors.append(
                    f"{config.relative_to(ROOT)} -> {module}@{ref}: undeclared input(s): {', '.join(extra)}"
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
    print(
        f"module-interface preflight passed: {checked} unit(s), {len(cache)} module/ref pair(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
