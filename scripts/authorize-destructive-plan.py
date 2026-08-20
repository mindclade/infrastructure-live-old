#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

#
"""Fail closed unless a destructive saved plan has explicit emergency/change authorization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

CHANGE_REFERENCE = re.compile(
    r"^(?:CHG|INC|SEC|DR)-[A-Z0-9][A-Z0-9-]{2,63}$", re.IGNORECASE
)


def as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("classification", type=Path)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--allow-destroy", default="false")
    parser.add_argument("--change-reference", default="")
    args = parser.parse_args()

    try:
        data = json.loads(args.classification.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read plan classification: {exc}", file=sys.stderr)
        return 2
    if data.get("schema_version") != "1.0.0" or not isinstance(
        data.get("destructive"), bool
    ):
        print("ERROR: unrecognized plan classification schema", file=sys.stderr)
        return 2
    if not data["destructive"]:
        print("destructive authorization: not required")
        return 0

    errors: list[str] = []
    if args.event_name != "workflow_dispatch":
        errors.append(
            "destructive plans may not auto-apply from a push; use protected workflow_dispatch"
        )
    if not as_bool(args.allow_destroy):
        errors.append("allow_destroy must be explicitly enabled")
    if not CHANGE_REFERENCE.fullmatch(args.change_reference.strip()):
        errors.append(
            "change_reference must match CHG-, INC-, SEC-, or DR- followed by a tracked identifier"
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        for item in data.get("destructive_changes", [])[:40]:
            print(
                f"DESTRUCTIVE: {item.get('classification')} {item.get('resource_type')} "
                f"{item.get('address')}",
                file=sys.stderr,
            )
        return 1

    print(
        "destructive authorization accepted: "
        f"reference={args.change_reference.strip().upper()} "
        f"critical={bool(data.get('critical_destructive'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
