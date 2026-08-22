#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Validate DNS evidence, exception metadata, and derived readiness gates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "contracts" / "dns-domain-inventory.json"
DEFAULT_EVIDENCE = ROOT / "contracts" / "dns-change-evidence.json"
DEFAULT_EXCEPTIONS = ROOT / "contracts" / "dns-public-record-exceptions.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GENERATION_URI = re.compile(r"^gs://[^#]+#[1-9][0-9]*$")
CHANGE_RECORD = re.compile(r"^CHG-[A-Za-z0-9._-]+$")
ADDRESS_TYPES = {"A", "AAAA", "CNAME"}
EXCEPTION_DOMAINS = {"mindclade.ai", "mindclade.dev"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def parse_timestamp(value: Any, field: str, errors: list[str]) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{field} must be an RFC3339 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be an RFC3339 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field} must include a timezone")
        return None
    return parsed.astimezone(timezone.utc)


def domain_map(payload: dict[str, Any], label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    entries = payload.get("domains")
    if not isinstance(entries, list):
        errors.append(f"{label}.domains must be an array")
        return {}
    result: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{label}.domains[{index}] must be an object")
            continue
        domain = entry.get("domain") or entry.get("name")
        if not isinstance(domain, str) or not domain:
            errors.append(f"{label}.domains[{index}] has no domain")
            continue
        if domain in result:
            errors.append(f"{label} contains duplicate domain {domain}")
            continue
        result[domain] = entry
    return result


def _metadata_is_empty(gate: dict[str, Any]) -> bool:
    return all(
        gate.get(field) is None
        for field in ("uri", "observed_at", "sha256", "reviewer", "reviewed_at", "expires_at")
    )


def validate_gate(
    gate: dict[str, Any],
    location: str,
    uri_prefix: str,
    as_of: datetime,
    errors: list[str],
) -> None:
    gate_id = gate.get("gate_id")
    phase = gate.get("phase")
    status = gate.get("status")
    if not isinstance(gate_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", gate_id):
        errors.append(f"{location}.gate_id is invalid")
    if phase not in {"inventory", "delegation"}:
        errors.append(f"{location}.phase is invalid")
    if status not in {"pending", "pending_upload", "pending_review", "approved", "rejected"}:
        errors.append(f"{location}.status is invalid")
        return
    uri = gate.get("uri")
    observed = parse_timestamp(gate.get("observed_at"), f"{location}.observed_at", errors)
    reviewed = parse_timestamp(gate.get("reviewed_at"), f"{location}.reviewed_at", errors)
    expires = parse_timestamp(gate.get("expires_at"), f"{location}.expires_at", errors)
    digest = gate.get("sha256")
    reviewer = gate.get("reviewer")
    if status == "pending":
        if not _metadata_is_empty(gate):
            errors.append(f"{location}: pending gates must not claim evidence metadata")
        return
    if not isinstance(uri, str) or not uri.startswith(uri_prefix):
        errors.append(f"{location}.uri must be under the immutable evidence prefix")
    if isinstance(uri, str) and (uri.startswith("file:") or "/private/tmp" in uri):
        errors.append(f"{location}.uri must not reference local temporary evidence")
    if observed is None:
        errors.append(f"{location}.observed_at is required")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        errors.append(f"{location}.sha256 must be a lowercase SHA-256")
    if status == "pending_upload":
        if isinstance(uri, str) and "#" in uri:
            errors.append(f"{location}.uri must not claim a generation before upload")
        if reviewer is not None or reviewed is not None or expires is not None:
            errors.append(f"{location}: pending_upload gates must not claim review metadata")
        return
    if not isinstance(uri, str) or not GENERATION_URI.fullmatch(uri):
        errors.append(f"{location}.uri must pin an immutable GCS object generation")
    if status == "pending_review":
        if reviewer is not None or reviewed is not None or expires is not None:
            errors.append(f"{location}: pending_review gates must not claim review metadata")
        return
    if not isinstance(reviewer, str) or "@" not in reviewer:
        errors.append(f"{location}.reviewer is required for {status}")
    if reviewed is None:
        errors.append(f"{location}.reviewed_at is required for {status}")
    if status == "approved" and expires is not None and expires <= as_of:
        errors.append(f"{location}: approved evidence expired at {gate.get('expires_at')}")


def validate_evidence_contract(
    evidence: dict[str, Any], inventory: dict[str, Any], as_of: datetime
) -> list[str]:
    errors: list[str] = []
    if evidence.get("schema_version") != 1:
        errors.append("evidence schema_version must be 1")
    store = evidence.get("evidence_store")
    if not isinstance(store, dict):
        return errors + ["evidence_store must be an object"]
    uri_prefix = store.get("uri_prefix")
    if not isinstance(uri_prefix, str) or not re.fullmatch(r"gs://[^/]+/.+/", uri_prefix):
        errors.append("evidence_store.uri_prefix must be a bucket object prefix ending in /")
        uri_prefix = "gs://invalid/"
    if store.get("retention_mode") != "locked":
        errors.append("evidence_store.retention_mode must be locked")
    if store.get("object_versioning_required") is not True:
        errors.append("evidence_store.object_versioning_required must be true")
    portfolio = evidence.get("portfolio_gates")
    if not isinstance(portfolio, list) or not portfolio:
        errors.append("portfolio_gates must be a non-empty array")
        portfolio = []
    seen: set[str] = set()
    for index, gate in enumerate(portfolio):
        if not isinstance(gate, dict):
            errors.append(f"portfolio_gates[{index}] must be an object")
            continue
        gate_id = gate.get("gate_id")
        if gate_id in seen:
            errors.append(f"duplicate portfolio gate {gate_id}")
        if isinstance(gate_id, str):
            seen.add(gate_id)
        validate_gate(gate, f"portfolio_gates[{index}]", uri_prefix, as_of, errors)
    inventory_domains = domain_map(inventory, "inventory", errors)
    evidence_domains = domain_map(evidence, "evidence", errors)
    if set(inventory_domains) != set(evidence_domains):
        errors.append("evidence domains must exactly match the canonical DNS inventory")
    for domain, entry in evidence_domains.items():
        gates = entry.get("gates")
        if not isinstance(gates, list) or not gates:
            errors.append(f"evidence.{domain}.gates must be a non-empty array")
            continue
        seen = set()
        phases: set[str] = set()
        for index, gate in enumerate(gates):
            if not isinstance(gate, dict):
                errors.append(f"evidence.{domain}.gates[{index}] must be an object")
                continue
            gate_id = gate.get("gate_id")
            if gate_id in seen:
                errors.append(f"duplicate evidence gate {domain}/{gate_id}")
            if isinstance(gate_id, str):
                seen.add(gate_id)
            if isinstance(gate.get("phase"), str):
                phases.add(gate["phase"])
            validate_gate(gate, f"evidence.{domain}.gates[{index}]", uri_prefix, as_of, errors)
        if phases != {"inventory", "delegation"}:
            errors.append(f"evidence.{domain} must define inventory and delegation gates")
    return errors


def _record_types(entry: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    seen_objects: set[int] = set()

    def visit(value: Any, implicit_key: str | None = None) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict) or id(value) in seen_objects:
            return
        seen_objects.add(id(value))
        record_type = value.get("type") or value.get("record_type") or value.get("rrtype")
        key = (
            value.get("key")
            or value.get("record_key")
            or value.get("record_map_key")
            or value.get("record_id")
            or value.get("id")
            or implicit_key
        )
        name = value.get("name")
        if isinstance(record_type, str) and not isinstance(key, str) and isinstance(name, str):
            key = f"{name.replace('@', 'apex')}-{record_type.lower()}"
        if isinstance(record_type, str) and isinstance(key, str):
            result.setdefault(key, []).append(record_type.upper())
        for child_key, child in value.items():
            if isinstance(child, dict):
                visit(child, child_key)
            elif isinstance(child, list):
                visit(child)

    visit(entry)
    return result


def validate_exception_contract(
    exceptions: dict[str, Any], inventory: dict[str, Any], as_of: datetime
) -> list[str]:
    errors: list[str] = []
    if exceptions.get("schema_version") != 1:
        errors.append("public-record exception schema_version must be 1")
    inventory_domains = domain_map(inventory, "inventory", errors)
    exception_domains = domain_map(exceptions, "exceptions", errors)
    if set(inventory_domains) != set(exception_domains):
        errors.append("exception domains must exactly match the canonical DNS inventory")
    for domain, inventory_entry in inventory_domains.items():
        allowlist = inventory_entry.get("public_record_allowlist", [])
        if not isinstance(allowlist, list) or not all(isinstance(key, str) for key in allowlist):
            errors.append(f"inventory.{domain}.public_record_allowlist must be an array of strings")
            allowlist = []
        entries = exception_domains.get(domain, {}).get("exceptions", [])
        if not isinstance(entries, list):
            errors.append(f"exceptions.{domain}.exceptions must be an array")
            entries = []
        keys: list[str] = []
        record_types = _record_types(inventory_entry)
        for index, exception in enumerate(entries):
            location = f"exceptions.{domain}.exceptions[{index}]"
            if not isinstance(exception, dict):
                errors.append(f"{location} must be an object")
                continue
            key = exception.get("record_key")
            record_type = exception.get("record_type")
            status = exception.get("review_status")
            if not isinstance(key, str) or not key:
                errors.append(f"{location}.record_key is required")
                continue
            keys.append(key)
            if domain not in EXCEPTION_DOMAINS:
                errors.append(f"{domain} may not define public address exceptions")
            if record_type not in ADDRESS_TYPES:
                errors.append(f"{location}.record_type must be A, AAAA, or CNAME")
            matching_types = record_types.get(key, [])
            if len(matching_types) != 1:
                errors.append(f"{location} must match exactly one canonical DNS record")
            elif record_type != matching_types[0]:
                errors.append(
                    f"{location}.record_type {record_type} does not match canonical {matching_types[0]}"
                )
            justification = exception.get("justification")
            if not isinstance(justification, str) or len(justification.strip()) < 20:
                errors.append(f"{location}.justification must explain the exception")
            if status not in {"pending_review", "approved", "rejected"}:
                errors.append(f"{location}.review_status is invalid")
                continue
            change_record = exception.get("change_record")
            approved_by = exception.get("approved_by")
            approved_at = parse_timestamp(
                exception.get("approved_at"), f"{location}.approved_at", errors
            )
            expires_at = parse_timestamp(
                exception.get("expires_at"), f"{location}.expires_at", errors
            )
            if status == "pending_review":
                if any(value is not None for value in (change_record, approved_by, approved_at, expires_at)):
                    errors.append(f"{location}: pending exceptions must not claim approval metadata")
            else:
                if not isinstance(change_record, str) or not CHANGE_RECORD.fullmatch(change_record):
                    errors.append(f"{location}.change_record is required after review")
                if not isinstance(approved_by, str) or "@" not in approved_by:
                    errors.append(f"{location}.approved_by is required after review")
                if approved_at is None:
                    errors.append(f"{location}.approved_at is required after review")
            if status == "approved" and expires_at is not None and expires_at <= as_of:
                errors.append(f"{location}: approved exception expired at {exception.get('expires_at')}")
        if len(keys) != len(set(keys)):
            errors.append(f"exceptions.{domain} contains duplicate record keys")
        if set(keys) != set(allowlist):
            errors.append(f"exceptions.{domain} must exactly match public_record_allowlist")
    return errors


def _gate_is_approved(gate: dict[str, Any], as_of: datetime) -> bool:
    if gate.get("status") != "approved":
        return False
    value = gate.get("expires_at")
    if value is None:
        return True
    errors: list[str] = []
    expires = parse_timestamp(value, "expires_at", errors)
    return expires is not None and not errors and expires > as_of


def derive_readiness(
    inventory: dict[str, Any],
    evidence: dict[str, Any],
    exceptions: dict[str, Any],
    as_of: datetime,
) -> dict[str, dict[str, Any]]:
    ignored_errors: list[str] = []
    inventory_domains = domain_map(inventory, "inventory", ignored_errors)
    evidence_domains = domain_map(evidence, "evidence", ignored_errors)
    exception_domains = domain_map(exceptions, "exceptions", ignored_errors)
    portfolio = [gate for gate in evidence.get("portfolio_gates", []) if isinstance(gate, dict)]
    portfolio_inventory = [gate for gate in portfolio if gate.get("phase") == "inventory"]
    portfolio_delegation = [gate for gate in portfolio if gate.get("phase") == "delegation"]
    result: dict[str, dict[str, Any]] = {}
    for domain, inventory_entry in inventory_domains.items():
        gates = evidence_domains.get(domain, {}).get("gates", [])
        gates = [gate for gate in gates if isinstance(gate, dict)]
        domain_inventory = [gate for gate in gates if gate.get("phase") == "inventory"]
        domain_delegation = [gate for gate in gates if gate.get("phase") == "delegation"]
        inventory_blockers = [
            f"portfolio/{gate.get('gate_id')}"
            for gate in portfolio_inventory
            if not _gate_is_approved(gate, as_of)
        ] + [
            f"{domain}/{gate.get('gate_id')}"
            for gate in domain_inventory
            if not _gate_is_approved(gate, as_of)
        ]
        inventory_complete = bool(portfolio_inventory and domain_inventory) and not inventory_blockers
        delegation_blockers = [
            f"portfolio/{gate.get('gate_id')}"
            for gate in portfolio_delegation
            if not _gate_is_approved(gate, as_of)
        ] + [
            f"{domain}/{gate.get('gate_id')}"
            for gate in domain_delegation
            if not _gate_is_approved(gate, as_of)
        ]
        allowlist = inventory_entry.get("public_record_allowlist", [])
        exception_entries = exception_domains.get(domain, {}).get("exceptions", [])
        approved_keys: set[str] = set()
        for exception in exception_entries:
            if not isinstance(exception, dict) or exception.get("review_status") != "approved":
                continue
            expiry_errors: list[str] = []
            expires = parse_timestamp(exception.get("expires_at"), "expires_at", expiry_errors)
            if not expiry_errors and (expires is None or expires > as_of):
                key = exception.get("record_key")
                if isinstance(key, str):
                    approved_keys.add(key)
        if set(allowlist) != approved_keys:
            delegation_blockers.append(f"{domain}/public_record_exception_approvals")
        delegation_ready = (
            inventory_complete
            and bool(portfolio_delegation and domain_delegation)
            and not delegation_blockers
        )
        result[domain] = {
            "inventory_complete": inventory_complete,
            "delegation_ready": delegation_ready,
            "inventory_blockers": sorted(inventory_blockers),
            "delegation_blockers": sorted(set(delegation_blockers)),
        }
    return result


def validate_declared_readiness(
    inventory: dict[str, Any], derived: dict[str, dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    domains = domain_map(inventory, "inventory", errors)
    for domain, entry in domains.items():
        for field in ("inventory_complete", "delegation_ready"):
            declared = entry.get(field)
            if not isinstance(declared, bool):
                errors.append(f"inventory.{domain}.{field} must be a boolean")
            elif declared != derived.get(domain, {}).get(field):
                errors.append(
                    f"inventory.{domain}.{field}={declared} does not match derived "
                    f"{derived.get(domain, {}).get(field)}"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    parser.add_argument("--as-of", help="RFC3339 evaluation time; defaults to current UTC")
    args = parser.parse_args()
    parse_errors: list[str] = []
    as_of = (
        parse_timestamp(args.as_of, "--as-of", parse_errors)
        if args.as_of
        else datetime.now(timezone.utc)
    )
    if parse_errors or as_of is None:
        for error in parse_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    try:
        inventory = load_json(args.inventory)
        evidence = load_json(args.evidence)
        exceptions = load_json(args.exceptions)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    errors = validate_evidence_contract(evidence, inventory, as_of)
    errors.extend(validate_exception_contract(exceptions, inventory, as_of))
    derived = derive_readiness(inventory, evidence, exceptions, as_of)
    errors.extend(validate_declared_readiness(inventory, derived))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    for domain in sorted(derived):
        state = derived[domain]
        print(
            f"{domain}: inventory_complete={str(state['inventory_complete']).lower()} "
            f"delegation_ready={str(state['delegation_ready']).lower()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
