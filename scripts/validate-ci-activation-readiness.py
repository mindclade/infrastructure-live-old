#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Validate CI activation lifecycle records and generate their source readiness view."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/ci-activation-readiness.json"
DOC = ROOT / "docs/generated/ci-activation-readiness.md"
EXPECTED = {
    "arc-on-demand-runners": ("complete", "blocked"),
    "arc-presubmit-spot": ("proposed", "blocked"),
    "bazel-remote-cache": ("complete", "blocked"),
    "bazel-remote-execution": ("complete", "blocked"),
    "nix-attic-cache": ("proposed", "blocked"),
}


def load_contract() -> dict:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("CI activation readiness must be an object")
    return value


def validate(document: dict, as_of: dt.date) -> list[str]:
    errors: list[str] = []
    if set(document) != {"schemaVersion", "evidenceMaxAgeDays", "capabilities"} or document.get("schemaVersion") != 1:
        errors.append("CI readiness root fields are not exact")
        return errors
    max_age = document.get("evidenceMaxAgeDays")
    if not isinstance(max_age, int) or not 1 <= max_age <= 365:
        errors.append("evidenceMaxAgeDays must be 1..365")
    capabilities = document.get("capabilities")
    if not isinstance(capabilities, list):
        return errors + ["capabilities must be a list"]
    indexed = {item.get("id"): item for item in capabilities if isinstance(item, dict)}
    if set(indexed) != set(EXPECTED) or len(indexed) != len(capabilities):
        errors.append("CI readiness capability inventory differs")
        return errors
    exact = {"id", "owner", "sourceState", "activationState", "sourcePaths", "blockers", "qualifiedAt", "evidenceExpiresAt", "evidenceSha256", "evidenceUri"}
    for capability_id, item in indexed.items():
        if set(item) != exact:
            errors.append(f"{capability_id}: fields are not exact")
            continue
        expected_source, expected_activation = EXPECTED[capability_id]
        if (item["sourceState"], item["activationState"]) != (expected_source, expected_activation):
            errors.append(f"{capability_id}: lifecycle differs from reviewed source state")
        if not isinstance(item["blockers"], list) or not item["blockers"]:
            errors.append(f"{capability_id}: blocked lifecycle must retain blockers")
        for relative in item.get("sourcePaths", []):
            if not ROOT.joinpath(relative).exists():
                errors.append(f"{capability_id}: source path is missing: {relative}")
        evidence = [item[name] for name in ("qualifiedAt", "evidenceExpiresAt", "evidenceSha256", "evidenceUri")]
        if all(value is None for value in evidence):
            continue
        if any(value is None for value in evidence):
            errors.append(f"{capability_id}: evidence metadata is incomplete")
            continue
        try:
            qualified = dt.date.fromisoformat(str(item["qualifiedAt"])[:10])
            expires = dt.date.fromisoformat(str(item["evidenceExpiresAt"])[:10])
        except ValueError:
            errors.append(f"{capability_id}: evidence dates are invalid")
            continue
        if expires <= qualified or (expires - qualified).days > max_age:
            errors.append(f"{capability_id}: evidence expiry exceeds the reviewed maximum age")
        if expires < as_of and item["activationState"] != "blocked":
            errors.append(f"{capability_id}: expired evidence must fail closed")
        digest = str(item["evidenceSha256"])
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            errors.append(f"{capability_id}: evidence digest is invalid")
        if not str(item["evidenceUri"]).startswith("gs://"):
            errors.append(f"{capability_id}: evidence must use the protected archive")

    nix = json.loads((ROOT / "contracts/nix-binary-cache.json").read_text(encoding="utf-8"))
    if nix.get("status") != "proposed" or nix.get("client", {}).get("enabled") is not False:
        errors.append("nix-attic-cache: detailed contract no longer matches fail-closed readiness")
    cache_doc = (ROOT / "5-workloads/ci/bazel-remote-cache/README.md").read_text(encoding="utf-8")
    if "Do not configure a Bazel client to upload" not in cache_doc:
        errors.append("bazel-remote-cache: upload activation hold is missing")
    remote = (ROOT / "_envcommon/bazel-remote-execution.hcl").read_text(encoding="utf-8")
    if 'capacity_type               = "ON_DEMAND"' not in remote:
        errors.append("bazel-remote-execution: reviewed on-demand capacity changed")
    return sorted(set(errors))


def render(document: dict) -> str:
    lines = [
        "<!-- generated by scripts/validate-ci-activation-readiness.py; do not edit -->",
        "",
        "# CI capability activation readiness",
        "",
        "This source view is generated from `contracts/ci-activation-readiness.json`. It does not prove deployment or qualification.",
        f"Connected evidence expires after at most {document['evidenceMaxAgeDays']} days.",
        "",
        "| Capability | Owner | Source | Activation | Evidence | Remaining blockers |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for item in sorted(document["capabilities"], key=lambda value: value["id"]):
        evidence = "not retained" if item["qualifiedAt"] is None else f"expires {item['evidenceExpiresAt']}"
        lines.append(f"| `{item['id']}` | {item['owner']} | {item['sourceState']} | {item['activationState']} | {evidence} | {len(item['blockers'])} |")
    lines.extend(["", "Activation remains blocked until every blocker is cleared through review and unexpired connected evidence is indexed.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=dt.date.fromisoformat, default=dt.date.today())
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        document = load_contract()
        errors = validate(document, args.as_of)
        if errors:
            raise ValueError("; ".join(errors))
        rendered = render(document)
        if args.write:
            DOC.parent.mkdir(parents=True, exist_ok=True)
            DOC.write_text(rendered, encoding="utf-8")
        if args.check and (not DOC.is_file() or DOC.read_text(encoding="utf-8") != rendered):
            raise ValueError("generated CI readiness documentation is stale; run with --write")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("CI activation readiness contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
