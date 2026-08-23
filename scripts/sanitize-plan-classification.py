#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Remove resource addresses and plan paths from a plan classification report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def sanitize(document: dict, commit: str, status: str = "complete") -> dict:
    summary = document.get("summary")
    if not isinstance(summary, dict) or set(summary) != {"create", "update", "delete", "replace", "read", "no-op"}:
        raise ValueError("plan classification summary is invalid")
    if not all(isinstance(value, int) and value >= 0 for value in summary.values()):
        raise ValueError("plan classification counts must be non-negative integers")
    destructive = document.get("destructive_changes")
    critical = document.get("critical_changes")
    if not isinstance(destructive, list) or not isinstance(critical, list):
        raise ValueError("plan classification risk lists are invalid")
    return {
        "schemaVersion": 1,
        "commit": commit,
        "status": status,
        "actions": {"noOp" if key == "no-op" else key: value for key, value in summary.items()},
        "risk": {
            "destructive": bool(document.get("destructive")),
            "destructiveChangeCount": len(destructive),
            "critical": bool(document.get("critical")),
            "criticalChangeCount": len(critical),
            "criticalDestructive": bool(document.get("critical_destructive")),
        },
        "planDocumentCount": len(document.get("plan_files", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("classification", type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        value = json.loads(args.classification.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("classification must be an object")
        args.output.write_text(json.dumps(sanitize(value, args.commit), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
