#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Generate deterministic, write-once DNS cutover packets from reviewed snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from validate_dns_governance import (
    DEFAULT_EVIDENCE,
    DEFAULT_EXCEPTIONS,
    DEFAULT_INVENTORY,
    derive_readiness,
    domain_map,
    load_json,
    parse_timestamp,
    validate_evidence_contract,
    validate_exception_contract,
)


CHANGE_RECORD = re.compile(r"^CHG-[A-Za-z0-9._-]+$")
DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_snapshot(directory: Path, domain: str) -> tuple[dict[str, Any], str]:
    path = directory / f"{domain}.json"
    snapshot = load_json(path)
    required = {
        "schema_version",
        "domain",
        "captured_at",
        "authoritative_nameservers",
        "parent_ds",
        "records",
    }
    if set(snapshot) != required:
        raise ValueError(f"{path} must contain exactly {sorted(required)}")
    if snapshot.get("schema_version") != 1 or snapshot.get("domain") != domain:
        raise ValueError(f"{path} has the wrong schema version or domain")
    nameservers = snapshot.get("authoritative_nameservers")
    if not isinstance(nameservers, list) or not nameservers or not all(
        isinstance(value, str) and value for value in nameservers
    ):
        raise ValueError(f"{path}.authoritative_nameservers must be a non-empty string array")
    if not isinstance(snapshot.get("parent_ds"), list) or not isinstance(
        snapshot.get("records"), list
    ):
        raise ValueError(f"{path}.parent_ds and records must be arrays")
    timestamp_errors: list[str] = []
    parse_timestamp(snapshot.get("captured_at"), f"{path}.captured_at", timestamp_errors)
    if timestamp_errors:
        raise ValueError("; ".join(timestamp_errors))
    return snapshot, file_sha256(path)


def _preflight_commands(domain: str, nameservers: list[str]) -> list[str]:
    commands = [f"dig +dnssec DS {domain} @a.gtld-servers.net"]
    for nameserver in nameservers:
        for record_type in ("SOA", "NS", "MX", "TXT", "CAA", "DNSKEY"):
            commands.append(f"dig +dnssec {record_type} {domain} @{nameserver}")
    return commands


def build_packets(
    *,
    inventory: dict[str, Any],
    evidence: dict[str, Any],
    exceptions: dict[str, Any],
    evidence_path: Path,
    incumbent_dir: Path,
    target_dir: Path,
    domains: list[str],
    generated_at: str,
    change_id: str,
    window_start: str,
    window_end: str,
    ttl_lowered_at: str,
    require_ready: bool = False,
) -> dict[str, dict[str, Any]]:
    if not CHANGE_RECORD.fullmatch(change_id):
        raise ValueError("change_id must be a safe CHG- identifier")
    timestamp_errors: list[str] = []
    generated = parse_timestamp(generated_at, "generated_at", timestamp_errors)
    start = parse_timestamp(window_start, "window_start", timestamp_errors)
    end = parse_timestamp(window_end, "window_end", timestamp_errors)
    lowered = parse_timestamp(ttl_lowered_at, "ttl_lowered_at", timestamp_errors)
    if timestamp_errors or None in (generated, start, end, lowered):
        raise ValueError("; ".join(timestamp_errors))
    assert generated is not None and start is not None and end is not None and lowered is not None
    if start >= end:
        raise ValueError("window_start must be before window_end")
    if start - lowered < timedelta(hours=48):
        raise ValueError("portable TTLs must be lowered at least 48 hours before the window")
    errors = validate_evidence_contract(evidence, inventory, generated)
    errors.extend(validate_exception_contract(exceptions, inventory, generated))
    if errors:
        raise ValueError("governance contracts are invalid: " + "; ".join(errors))
    inventory_domains = domain_map(inventory, "inventory", [])
    exception_domains = domain_map(exceptions, "exceptions", [])
    readiness = derive_readiness(inventory, evidence, exceptions, generated)
    evidence_digest = file_sha256(evidence_path)
    packets: dict[str, dict[str, Any]] = {}
    for domain in domains:
        if not DOMAIN.fullmatch(domain) or domain not in inventory_domains:
            raise ValueError(f"domain is not in the canonical inventory: {domain}")
        state = readiness[domain]
        if require_ready and not state["delegation_ready"]:
            raise ValueError(f"{domain} is not delegation-ready: {state['delegation_blockers']}")
        incumbent, incumbent_hash = load_snapshot(incumbent_dir, domain)
        target, target_hash = load_snapshot(target_dir, domain)
        all_nameservers = list(
            dict.fromkeys(
                incumbent["authoritative_nameservers"] + target["authoritative_nameservers"]
            )
        )
        packets[domain] = {
            "schema_version": 1,
            "status": "READY" if state["delegation_ready"] else "DRAFT",
            "domain": domain,
            "change_id": change_id,
            "generated_at": generated_at,
            "window": {"start": window_start, "end": window_end},
            "ttl_lowered_at": ttl_lowered_at,
            "readiness": state,
            "evidence_manifest_sha256": evidence_digest,
            "public_record_exceptions": exception_domains[domain].get("exceptions", []),
            "incumbent_snapshot": {"sha256": incumbent_hash, "content": incumbent},
            "target_snapshot": {"sha256": target_hash, "content": target},
            "preflight_commands": _preflight_commands(domain, all_nameservers),
            "cutover_steps": [
                "Confirm the change window is open and the incumbent zone freeze is active.",
                "Run every preflight command and attach complete output to the change record.",
                "Confirm parent DS state directly before changing delegation.",
                "Change registrar nameservers manually to the target snapshot nameservers.",
                "Validate authoritative answers and service behavior before publishing target DS data.",
                "Publish target DS data manually, then rerun DNSSEC and service checks."
            ],
            "rollback_steps": [
                "If target DS was published, remove it and wait until parent-authoritative queries show no DS.",
                "Restore the incumbent snapshot nameservers manually.",
                "Confirm incumbent DNSKEY and authoritative answers are visible.",
                "Restore the incumbent DS only when it matches the visible incumbent DNSKEY.",
                "Keep both zones unchanged and attach rollback evidence to the change record."
            ]
        }
    return packets


def write_packets(packets: dict[str, dict[str, Any]], output_dir: Path) -> None:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing cutover packet directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    os.chmod(staging, 0o700)
    try:
        checksums: list[str] = []
        for domain in sorted(packets):
            filename = f"{domain}.cutover.json"
            content = canonical_bytes(packets[domain])
            path = staging / filename
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
            checksums.append(f"{hashlib.sha256(content).hexdigest()}  {filename}")
        checksum_content = ("\n".join(checksums) + "\n").encode("ascii")
        checksum_path = staging / "SHA256SUMS"
        descriptor = os.open(checksum_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(checksum_content)
        os.replace(staging, output_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    parser.add_argument("--incumbent-snapshot-dir", type=Path, required=True)
    parser.add_argument("--target-snapshot-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--domain", action="append", dest="domains")
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--change-id", required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--ttl-lowered-at", required=True)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        inventory = load_json(args.inventory)
        evidence = load_json(args.evidence)
        exceptions = load_json(args.exceptions)
        domains = args.domains or sorted(domain_map(inventory, "inventory", []))
        packets = build_packets(
            inventory=inventory,
            evidence=evidence,
            exceptions=exceptions,
            evidence_path=args.evidence,
            incumbent_dir=args.incumbent_snapshot_dir,
            target_dir=args.target_snapshot_dir,
            domains=domains,
            generated_at=args.generated_at,
            change_id=args.change_id,
            window_start=args.window_start,
            window_end=args.window_end,
            ttl_lowered_at=args.ttl_lowered_at,
            require_ready=args.require_ready,
        )
        write_packets(packets, args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"wrote {len(packets)} immutable cutover packet(s) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
