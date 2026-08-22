#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Compare delegated public DNS with read-only Cloud DNS snapshots for ready domains."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from check_dns_delegation import (
    canonical_rdata,
    evaluate_delegation,
    load_authoritative_snapshot,
)
from validate_dns_portfolio import (
    DEFAULT_INVENTORY,
    InventoryError,
    load_inventory,
    validate_inventory,
)


def _cloud_nameservers(domain: str, records: list[dict[str, Any]]) -> list[str]:
    apex = domain.rstrip(".") + "."
    for record in records:
        if record["name"] == apex and record["type"] == "NS":
            return sorted(
                canonical_rdata("NS", value) for value in record["rrdatas"]
            )
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL",
        "domains": [],
        "errors": [],
    }
    errors: list[str] = []
    try:
        inventory = load_inventory(args.inventory)
    except InventoryError as exc:
        inventory = {}
        errors.append(str(exc))
    if inventory:
        errors.extend(validate_inventory(inventory))
    if shutil.which("dig") is None:
        errors.append("dig is unavailable; enter the pinned Nix shell")

    ready_domains = []
    if inventory:
        ready_domains = [
            domain["domain"]
            for domain in inventory["domains"]
            if domain.get("delegation_ready") is True
        ]
    for domain in sorted(ready_domains):
        snapshot_path = args.snapshot_dir / f"{domain}.json"
        domain_report: dict[str, Any] = {
            "domain": domain,
            "status": "FAIL",
            "checks": [],
            "errors": [],
        }
        try:
            records = load_authoritative_snapshot(snapshot_path)
            nameservers = _cloud_nameservers(domain, records)
            if not nameservers:
                raise ValueError("Cloud DNS snapshot has no apex NS record set")
            checks = evaluate_delegation(
                inventory,
                domain,
                "postcutover",
                [],
                nameservers,
                True,
                authoritative_records=records,
            )
            domain_report["checks"] = checks
            if all(check["passed"] for check in checks):
                domain_report["status"] = "PASS"
            else:
                domain_report["errors"].append(
                    "one or more public DNS checks failed"
                )
        except ValueError as exc:
            domain_report["errors"].append(str(exc))
        report["domains"].append(domain_report)

    report["errors"] = sorted(set(errors))
    failed = errors or any(
        domain["status"] != "PASS" for domain in report["domains"]
    )
    report["status"] = "FAIL" if failed else "PASS"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if failed:
        print(f"DNS portfolio monitoring failed; evidence={args.output}", file=sys.stderr)
        return 1
    if not ready_domains:
        print("DNS portfolio monitoring passed; no domains are delegation-ready")
    else:
        print(
            "DNS portfolio monitoring passed; domains="
            + ",".join(sorted(ready_domains))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
