#!/usr/bin/env python3
"""Validate literal Terragrunt dependency paths and the numbered layer DAG."""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = {"development", "staging", "production"}
errors: list[str] = []


def layer(path: Path) -> int | None:
    match = re.match(r"(\d)-", path.parts[0]) if path.parts else None
    return int(match.group(1)) if match else None


def environment(path: Path) -> str | None:
    for part in path.parts:
        if part in ENVIRONMENTS:
            return part
    return None


for config in ROOT.rglob("terragrunt.hcl"):
    if any(part in {".git", ".terraform", ".terragrunt-cache"} for part in config.parts):
        continue
    relative = config.relative_to(ROOT)
    source_layer = layer(relative)
    source_env = environment(relative)
    text = config.read_text(encoding="utf-8")

    for raw in re.findall(r'config_path\s*=\s*"([^"]+)"', text):
        target = (config.parent / raw).resolve()
        try:
            target_relative = target.relative_to(ROOT)
        except ValueError:
            errors.append(f"{relative}: dependency escapes repository: {raw}")
            continue
        if not (target / "terragrunt.hcl").is_file():
            errors.append(f"{relative}: dependency target is missing: {target_relative}")
            continue

        target_layer = layer(target_relative)
        if source_layer is not None and target_layer is not None and target_layer > source_layer:
            errors.append(f"{relative}: backward dependency on {target_relative}")

        target_env = environment(target_relative)
        if source_env and target_env and source_env != target_env:
            errors.append(
                f"{relative}: cross-environment dependency {source_env} -> {target_env}: "
                f"{target_relative}"
            )

if errors:
    for message in sorted(set(errors)):
        print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)
print("dependency paths and layer invariants passed")
