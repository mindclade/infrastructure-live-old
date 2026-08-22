#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Run read-only DNS delegation preflight and post-cutover checks."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from validate_dns_portfolio import (
    DEFAULT_INVENTORY,
    InventoryError,
    load_inventory,
    validate_inventory,
)


CHANGE_REFERENCE = re.compile(r"^(?:CHG|INC|SEC|DR)-[A-Za-z0-9][A-Za-z0-9._-]*$")
NAMESERVER = re.compile(
    r"^(?=.{1,253}\.?$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}\.?$"
)
Resolver = Callable[
    [Optional[str], str, str], Tuple[List[str], Optional[str]]
]


def parse_nameservers(raw: str) -> list[str]:
    """Parse a comma/whitespace list into unique canonical nameserver names."""

    result: list[str] = []
    for value in re.split(r"[\s,]+", raw.strip()):
        if not value:
            continue
        if not NAMESERVER.fullmatch(value):
            raise ValueError(f"invalid nameserver: {value}")
        canonical = value.rstrip(".").lower() + "."
        if canonical not in result:
            result.append(canonical)
    return result


def owner_fqdn(owner: str, domain: str) -> str:
    return f"{domain}." if owner in {"", "@"} else f"{owner}.{domain}."


def canonical_rdata(record_type: str, value: str) -> str:
    """Normalize presentation differences without changing case-sensitive TXT content."""

    value = value.strip()
    record_type = record_type.upper()
    if record_type == "TXT":
        chunks = re.findall(r'"((?:\\.|[^"\\])*)"', value)
        if chunks:
            decoded: list[str] = []
            for chunk in chunks:
                try:
                    decoded.append(json.loads(f'"{chunk}"'))
                except json.JSONDecodeError:
                    decoded.append(chunk)
            return "".join(decoded)
        return value
    value = " ".join(value.split())
    if record_type in {"NS", "CNAME"}:
        return value.rstrip(".").lower() + "."
    if record_type == "MX":
        parts = value.split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            target = "." if parts[1] == "." else parts[1].rstrip(".").lower() + "."
            return f"{parts[0]} {target}"
    return value


def load_authoritative_snapshot(path: Path) -> list[dict[str, Any]]:
    """Load a Cloud DNS record-set snapshot produced by a read-only gcloud command."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read authoritative snapshot {path}: {exc}") from exc
    if not isinstance(value, list):
        raise ValueError("authoritative snapshot must be a JSON list")
    records: list[dict[str, Any]] = []
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            raise ValueError(f"authoritative snapshot record {index} must be an object")
        name = record.get("name")
        record_type = record.get("type")
        rrdatas = record.get("rrdatas")
        if not isinstance(name, str) or not isinstance(record_type, str):
            raise ValueError(f"authoritative snapshot record {index} requires name and type")
        if not isinstance(rrdatas, list) or not all(isinstance(item, str) for item in rrdatas):
            raise ValueError(f"authoritative snapshot record {index}.rrdatas must be strings")
        records.append(
            {
                "name": name.rstrip(".") + ".",
                "type": record_type.upper(),
                "rrdatas": rrdatas,
            }
        )
    return records


def parent_zone(domain_name: str) -> str:
    """Return the parent zone for the portfolio's one-label-TLD apex domains."""

    labels = domain_name.rstrip(".").split(".")
    if len(labels) != 2:
        raise ValueError("portfolio domains must be registrable apex names with one-label TLDs")
    return labels[-1] + "."


def dig_query(server: str | None, name: str, record_type: str) -> tuple[list[str], str | None]:
    command = ["dig"]
    if server:
        command.append(f"@{server.rstrip('.')}")
    command.extend(
        [
            name,
            record_type,
            "+time=5",
            "+tries=1",
            "+noall",
            "+answer",
            "+nocomments",
            "+nocmd",
            "+nostats",
        ]
    )
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"dig exited {result.returncode}"
        return [], detail
    answers: list[str] = []
    for line in result.stdout.splitlines():
        fields = line.split(None, 4)
        if len(fields) == 5 and fields[3].upper() == record_type.upper():
            answers.append(canonical_rdata(record_type, fields[4]))
    return sorted(set(answers)), None


def _check(
    checks: list[dict[str, Any]],
    name: str,
    expected: list[str] | str,
    actual: list[str] | str,
    error: str | None = None,
) -> None:
    passed = error is None and actual == expected
    item: dict[str, Any] = {
        "name": name,
        "passed": passed,
        "expected": expected,
        "actual": actual,
    }
    if error:
        item["error"] = error
    checks.append(item)


def _presence_check(
    checks: list[dict[str, Any]],
    name: str,
    actual: list[str],
    error: str | None,
) -> None:
    item: dict[str, Any] = {
        "name": name,
        "passed": error is None and bool(actual),
        "expected": "one-or-more-answers",
        "actual": actual,
    }
    if error:
        item["error"] = error
    checks.append(item)


def evaluate_delegation(
    inventory: dict[str, Any],
    domain_name: str,
    phase: str,
    incumbent_nameservers: list[str],
    cloud_nameservers: list[str],
    expect_dnssec: bool,
    resolver: Resolver = dig_query,
    authoritative_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return structured checks; this function performs no mutations."""

    checks: list[dict[str, Any]] = []
    domains = {
        domain["domain"]: domain
        for domain in inventory["domains"]
        if isinstance(domain, dict) and isinstance(domain.get("domain"), str)
    }
    domain = domains[domain_name]
    # Preflight compares the reviewed portable inventory between providers. SOA and apex NS
    # are provider-owned and necessarily differ before delegation. Predeligation and
    # postcutover instead use the complete Cloud DNS snapshot, including generated
    # Certificate Manager CNAMEs and provider-owned record sets.
    records = authoritative_records if phase != "preflight" else None
    records = records or [
        {
            "name": owner_fqdn(record["name"], domain_name),
            "type": record["type"],
            "rrdatas": record["rrdatas"],
        }
        for record in domain["records"]
    ]

    def compare_records(group: str, nameservers: list[str]) -> None:
        for nameserver in nameservers:
            for record in records:
                record_type = record["type"].upper()
                fqdn = record["name"]
                actual, error = resolver(nameserver, fqdn, record_type)
                expected = sorted(
                    canonical_rdata(record_type, value)
                    for value in record["rrdatas"]
                )
                _check(
                    checks,
                    f"{group}:{nameserver}:{fqdn}:{record_type}",
                    expected,
                    actual,
                    error,
                )

    if phase == "preflight":
        for group, nameservers in (
            ("incumbent", incumbent_nameservers),
            ("cloud", cloud_nameservers),
        ):
            for nameserver in nameservers:
                soa, error = resolver(nameserver, f"{domain_name}.", "SOA")
                _presence_check(checks, f"{group}:{nameserver}:SOA", soa, error)
            compare_records(group, nameservers)
        return checks

    if phase == "predeligation":
        parent = parent_zone(domain_name)
        parent_nameservers, error = resolver(None, parent, "NS")
        _presence_check(checks, f"parent:{parent}:NS", parent_nameservers, error)
        for nameserver in parent_nameservers:
            ds, error = resolver(nameserver, f"{domain_name}.", "DS")
            _check(
                checks,
                f"parent:{nameserver}:{domain_name}.:DS-absent",
                [],
                ds,
                error,
            )
        for nameserver in cloud_nameservers:
            soa, error = resolver(nameserver, f"{domain_name}.", "SOA")
            _presence_check(checks, f"cloud:{nameserver}:SOA", soa, error)
            dnskey, error = resolver(nameserver, f"{domain_name}.", "DNSKEY")
            _presence_check(checks, f"cloud:{nameserver}:DNSKEY", dnskey, error)
        compare_records("cloud", cloud_nameservers)
        return checks

    public_ns, error = resolver(None, f"{domain_name}.", "NS")
    _check(
        checks,
        "public-delegation:NS",
        sorted(cloud_nameservers),
        sorted(public_ns),
        error,
    )
    for nameserver in cloud_nameservers:
        soa, error = resolver(nameserver, f"{domain_name}.", "SOA")
        _presence_check(checks, f"cloud:{nameserver}:SOA", soa, error)
    for record in records:
        record_type = record["type"].upper()
        fqdn = record["name"]
        actual, error = resolver(None, fqdn, record_type)
        expected = sorted(
            canonical_rdata(record_type, value) for value in record["rrdatas"]
        )
        _check(checks, f"public:{fqdn}:{record_type}", expected, actual, error)
    if expect_dnssec:
        ds, error = resolver(None, f"{domain_name}.", "DS")
        _presence_check(checks, "public-dnssec:DS", ds, error)
        for nameserver in cloud_nameservers:
            dnskey, error = resolver(nameserver, f"{domain_name}.", "DNSKEY")
            _presence_check(checks, f"cloud:{nameserver}:DNSKEY", dnskey, error)
    return checks


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--domain", required=True)
    parser.add_argument(
        "--phase",
        required=True,
        choices=("preflight", "predeligation", "postcutover"),
    )
    parser.add_argument("--incumbent-nameservers", default="")
    parser.add_argument("--cloud-nameservers", required=True)
    parser.add_argument("--expect-dnssec", action="store_true")
    parser.add_argument("--authoritative-snapshot", type=Path)
    parser.add_argument("--change-reference", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domain": args.domain,
        "phase": args.phase,
        "change_reference": args.change_reference,
        "checks": [],
        "status": "FAIL",
    }
    errors: list[str] = []
    if not CHANGE_REFERENCE.fullmatch(args.change_reference):
        errors.append("change reference must start with CHG-, INC-, SEC-, or DR-")
    if args.phase in {"preflight", "predeligation"} and args.expect_dnssec:
        errors.append(
            f"{args.phase} must not expect a registrar DS record before delegation"
        )
    try:
        incumbent = parse_nameservers(args.incumbent_nameservers)
        cloud = parse_nameservers(args.cloud_nameservers)
    except ValueError as exc:
        errors.append(str(exc))
        incumbent, cloud = [], []
    if not cloud:
        errors.append("at least one Cloud DNS nameserver is required")
    if args.phase == "preflight" and not incumbent:
        errors.append("preflight requires at least one incumbent nameserver")
    if shutil.which("dig") is None:
        errors.append("dig is unavailable; enter the pinned Nix shell")

    try:
        inventory = load_inventory(args.inventory)
    except InventoryError as exc:
        inventory = {}
        errors.append(str(exc))
    if inventory:
        errors.extend(validate_inventory(inventory, {args.domain}))

    authoritative_records: list[dict[str, Any]] | None = None
    if args.authoritative_snapshot is not None:
        try:
            authoritative_records = load_authoritative_snapshot(
                args.authoritative_snapshot
            )
        except ValueError as exc:
            errors.append(str(exc))
    if args.phase == "predeligation" and not authoritative_records:
        errors.append(
            "predeligation requires a non-empty Cloud DNS authoritative snapshot"
        )

    if not errors:
        report["checks"] = evaluate_delegation(
            inventory,
            args.domain,
            args.phase,
            incumbent,
            cloud,
            args.expect_dnssec,
            authoritative_records=authoritative_records,
        )
        if all(check["passed"] for check in report["checks"]):
            report["status"] = "PASS"
        else:
            errors.append("one or more DNS checks failed")
    report["errors"] = sorted(set(errors))
    write_report(args.output, report)

    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"DNS {args.phase} failed; evidence={args.output}", file=sys.stderr)
        return 1
    print(f"DNS {args.phase} passed; evidence={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
