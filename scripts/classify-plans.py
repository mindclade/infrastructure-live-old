#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

#
"""Classify Terraform JSON plans for destructive and critical changes.

This is an enforcement input, not a presentation-only parser. Unknown or malformed plan JSON
fails closed so a production apply cannot proceed on an unclassified plan bundle.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

CRITICAL_TYPES = {
    "google_access_context_manager_service_perimeter",
    "google_billing_budget",
    "google_compute_firewall_policy",
    "google_compute_firewall_policy_rule",
    "google_compute_network",
    "google_compute_subnetwork",
    "google_container_cluster",
    "google_folder",
    "google_kms_crypto_key",
    "google_kms_key_ring",
    "google_logging_folder_sink",
    "google_logging_organization_sink",
    "google_logging_project_sink",
    "google_org_policy_policy",
    "google_organization_policy",
    "google_project",
    "google_project_service",
    "google_sql_database_instance",
    "google_storage_bucket",
}
SKIP_NAMES = {"ACCOUNT_RUNTIME.json", "RUN_CONTEXT.json", "PLAN_CLASSIFICATION.json"}


def classify_actions(actions: list[str]) -> str:
    aset = set(actions)
    if "delete" in aset and "create" in aset:
        return "replace"
    if "delete" in aset:
        return "delete"
    if "create" in aset:
        return "create"
    if "update" in aset:
        return "update"
    if "read" in aset:
        return "read"
    return "no-op"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan_root = args.plan_root.resolve()
    if not plan_root.is_dir():
        print(f"ERROR: plan root does not exist: {plan_root}", file=sys.stderr)
        return 2

    documents: list[tuple[Path, dict]] = []
    errors: list[str] = []
    for path in sorted(plan_root.rglob("*.json")):
        if path.name in SKIP_NAMES:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON {path.relative_to(plan_root)}: {exc}")
            continue
        if not isinstance(value, dict):
            continue
        # Terragrunt may place supporting JSON in the output tree. A Terraform plan JSON is
        # identified by its format version and resource_changes field.
        if "format_version" in value and "resource_changes" in value:
            documents.append((path, value))

    if not documents:
        errors.append("no Terraform plan JSON documents were generated")

    counts = {
        name: 0 for name in ("create", "update", "delete", "replace", "read", "no-op")
    }
    destructive_changes: list[dict] = []
    critical_changes: list[dict] = []
    plan_files: list[str] = []

    for path, document in documents:
        relative = str(path.relative_to(plan_root))
        plan_files.append(relative)
        resource_changes = document.get("resource_changes")
        if not isinstance(resource_changes, list):
            errors.append(f"{relative}: resource_changes is not a list")
            continue
        for entry in resource_changes:
            if not isinstance(entry, dict):
                errors.append(f"{relative}: malformed resource change entry")
                continue
            change = entry.get("change")
            actions = change.get("actions") if isinstance(change, dict) else None
            if not isinstance(actions, list) or not all(
                isinstance(action, str) for action in actions
            ):
                errors.append(
                    f"{relative}: {entry.get('address', '<unknown>')} has invalid actions"
                )
                continue
            classification = classify_actions(actions)
            counts[classification] += 1
            resource_type = str(entry.get("type", ""))
            record = {
                "address": str(entry.get("address", "")),
                "actions": actions,
                "classification": classification,
                "critical": resource_type in CRITICAL_TYPES,
                "module_address": entry.get("module_address"),
                "plan_file": relative,
                "resource_type": resource_type,
            }
            if classification in {"delete", "replace"}:
                destructive_changes.append(record)
            if record["critical"] and classification != "no-op":
                critical_changes.append(record)

    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    destructive_changes.sort(key=lambda item: (item["plan_file"], item["address"]))
    critical_changes.sort(key=lambda item: (item["plan_file"], item["address"]))
    critical_destructive = [item for item in destructive_changes if item["critical"]]
    result = {
        "schema_version": "1.0.0",
        "plan_files": sorted(plan_files),
        "summary": counts,
        "destructive": bool(destructive_changes),
        "critical": bool(critical_changes),
        "critical_destructive": bool(critical_destructive),
        "destructive_changes": destructive_changes,
        "critical_changes": critical_changes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "plan classification: "
        f"create={counts['create']} update={counts['update']} "
        f"delete={counts['delete']} replace={counts['replace']} "
        f"critical={len(critical_changes)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
