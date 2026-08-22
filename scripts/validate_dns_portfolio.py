#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Validate the DNS portfolio inventory and its live Terragrunt record maps.

The inventory is allowed to describe a deliberately blocked migration. A domain may become
delegation-ready only after its authoritative inventory is complete, its blockers are empty,
and every policy check passes. This lets normal CI enforce a fail-closed pending state without
pretending that an incomplete zone is ready to delegate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = (
    ROOT / "contracts/dns-domain-inventory.json"
)
DEFAULT_SCHEMA = ROOT / "contracts/dns-domain-inventory.schema.json"
DEFAULT_REVIEWED_RECORD_PINS = ROOT / "contracts/dns-reviewed-record-pins.json"
DEFAULT_REVIEWED_RECORD_PINS_SCHEMA = (
    ROOT / "contracts/dns-reviewed-record-pins.schema.json"
)
PUBLIC_ZONES = ROOT / "3-networks/shared/public-zones"
SHARED_DNS_HUB = ROOT / "3-networks/shared/dns-hub/terragrunt.hcl"

EXPECTED_DOMAINS = {
    "mindclade.com": ("corporate-identity-email-trust", "google-workspace"),
    "mindclade.ai": ("production-product-api-auth", "no-mail"),
    "mindclade.dev": ("developer-documentation-sdks", "no-mail"),
    "mindclade.studio": ("isolated-demos-experiments", "no-mail"),
}
EXPECTED_REGISTRAR = "squarespace"
EXPECTED_DNS = "google-cloud-dns"
EXPECTED_DNS_PROJECT = "mc-common-dns"
EXPECTED_MODULE_REPOSITORY = "mindclade/mindclade-internal-monorepo"
EXPECTED_MODULE_PATH = "infra/terraform/modules/dns"
EXPECTED_ENVIRONMENT_NAMING = {
    "production": "<service>.mindclade.ai",
    "staging": "<service>.staging.mindclade.ai",
    "development": "<service>.dev.mindclade.ai",
    "wildcard_production_records_allowed": False,
}
EXPECTED_HOSTNAMES = {
    "production": {
        "ai": ["api.mindclade.ai", "train.mindclade.ai", "models.mindclade.ai"],
        "developer": [
            "docs.mindclade.dev",
            "sdk.mindclade.dev",
            "go.mindclade.dev",
            "goproxy.mindclade.dev",
        ],
        "studio": ["mindclade.studio"],
    },
    "staging": {
        "ai": [
            "api.staging.mindclade.ai",
            "train.staging.mindclade.ai",
            "models.staging.mindclade.ai",
        ],
        "developer": [
            "docs.staging.mindclade.dev",
            "sdk.staging.mindclade.dev",
            "go.staging.mindclade.dev",
            "goproxy.staging.mindclade.dev",
        ],
        "studio": ["staging.mindclade.studio"],
    },
    "development": {
        "ai": [
            "api.dev.mindclade.ai",
            "train.dev.mindclade.ai",
            "models.dev.mindclade.ai",
        ],
        "developer": [
            "docs.dev.mindclade.dev",
            "sdk.dev.mindclade.dev",
            "go.dev.mindclade.dev",
            "goproxy.dev.mindclade.dev",
        ],
        "studio": ["dev.mindclade.studio"],
    },
}
ENVIRONMENT_ALIGNMENT_BLOCKER = "consumer-environment-hostnames-not-aligned"
CERTIFICATE_DOMAINS = {"mindclade.ai", "mindclade.dev", "mindclade.studio"}
EXPECTED_CERTIFICATE_OWNER = "infrastructure-live"
EXPECTED_CERTIFICATE_SERVICE = "google-certificate-manager"
EXPECTED_CERTIFICATE_NAMES = {
    "ai": "cert-mindclade-ai",
    "developer": "cert-mindclade-dev",
    "studio": "cert-mindclade-studio",
}
EXPECTED_CAA = {
    '0 issue "pki.goog"',
    '0 issue "letsencrypt.org"',
    '0 issuewild ";"',
    '0 iodef "mailto:security@mindclade.com"',
}
MODULE_PUBLIC_TYPES = {"CAA", "MX", "NS", "TXT"}
MODULE_CONDITIONAL_PUBLIC_TYPES = {"A", "AAAA", "CNAME"}
MODULE_SUPPORTED_PUBLIC_TYPES = MODULE_PUBLIC_TYPES | MODULE_CONDITIONAL_PUBLIC_TYPES
APPROVED_PUBLIC_RECORDS = {
    "mindclade.ai": {
        "apex-a": (
            "@",
            "A",
            300,
            (
                "198.185.159.144",
                "198.185.159.145",
                "198.49.23.144",
                "198.49.23.145",
            ),
        ),
        "www-cname": ("www", "CNAME", 300, ("ext-sq.squarespace.com.",)),
    },
    "mindclade.dev": {
        "apex-a": (
            "@",
            "A",
            300,
            (
                "198.185.159.144",
                "198.185.159.145",
                "198.49.23.144",
                "198.49.23.145",
            ),
        ),
        "www-cname": ("www", "CNAME", 300, ("ext-sq.squarespace.com.",)),
    },
}
APPROVED_PUBLIC_RECORD_ALLOWLISTS = {
    domain: set(APPROVED_PUBLIC_RECORDS.get(domain, {}))
    for domain in EXPECTED_DOMAINS
}
FINAL_WORKSPACE_SPF = "v=spf1 include:_spf.google.com -all"
FINAL_WORKSPACE_DMARC = (
    "v=DMARC1; p=reject; sp=reject; pct=100; adkim=s; aspf=s; "
    "rua=mailto:security@mindclade.com"
)
MODULE_RELEASE_STATUSES = {"planned", "published"}
MODULE_RELEASE_BLOCKER = "dns-module-ref-not-published"
MIGRATION_WINDOW_BLOCKER = "migration-window-not-approved"
CERTIFICATE_BLOCKERS = {
    "dns_authorizations_ready": "certificate-manager-dns-authorizations-not-ready",
    "issuer_inventory_complete": "certificate-issuer-inventory-not-reviewed",
    "caa_policy_ready": "certificate-caa-policy-not-ready",
}
RECORD_NAME = re.compile(
    r"^(?:@|[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?(?:\."
    r"[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?)*)$",
    re.IGNORECASE,
)
BLOCKER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_REF = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
CHANGE_REFERENCE = re.compile(r"^(?:CHG|INC|SEC|DR)-[A-Za-z0-9][A-Za-z0-9._-]*$")
RECORD_PINS_LOAD_ERROR = "DNS-PINS-001"
RECORD_PINS_ROOT_ERROR = "DNS-PINS-002"
RECORD_PINS_SCHEMA_ERROR = "DNS-PINS-003"
RECORD_PIN_MISSING_ERROR = "DNS-PINS-101"
RECORD_PIN_TTL_ERROR = "DNS-PINS-102"
RECORD_PIN_RRDATA_ERROR = "DNS-PINS-103"
RECORD_PIN_FAMILY_ERROR = "DNS-PINS-104"


class InventoryError(ValueError):
    """Raised when the normalized inventory cannot be read safely."""


def load_inventory(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read inventory {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InventoryError("inventory root must be a JSON object")
    return value


def load_reviewed_record_pins(
    path: Path = DEFAULT_REVIEWED_RECORD_PINS,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InventoryError(
            f"[{RECORD_PINS_LOAD_ERROR}] cannot read reviewed record-pins contract {path}"
        ) from exc
    if not isinstance(value, dict):
        raise InventoryError(
            f"[{RECORD_PINS_ROOT_ERROR}] reviewed record-pins root must be a JSON object"
        )
    return value


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return value


def _record_sets(domain: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    records = domain.get("records", [])
    if not isinstance(records, list):
        return result
    for record in records:
        if not isinstance(record, dict):
            continue
        name = record.get("name")
        record_type = record.get("type")
        if isinstance(name, str) and isinstance(record_type, str):
            result[(name.lower(), record_type.upper())] = record
    return result


def _txt_values(records: dict[tuple[str, str], dict[str, Any]], name: str) -> list[str]:
    record = records.get((name.lower(), "TXT"), {})
    return _strings(record.get("rrdatas"))


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _record_map_key(owner: str, record_type: str) -> str:
    return f"{owner.replace('@', 'apex')}-{record_type.lower()}"


def _json_path(parts: Any) -> str:
    result = "$"
    for part in parts:
        result += f"[{part}]" if isinstance(part, int) else f".{part}"
    return result


def _json_schema_diagnostics(
    document: dict[str, Any], schema_path: Path, label: str
) -> tuple[list[tuple[str, str, str]], str | None]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from jsonschema.exceptions import SchemaError
    except ImportError as exc:
        return [], (
            "JSON Schema validation requires the pinned jsonschema package from "
            f"`nix develop .#ci`: {exc}"
        )

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"cannot read {label} schema {schema_path}: {exc}"

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [], f"invalid {label} schema {schema_path}: {exc.message}"

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    violations = sorted(
        validator.iter_errors(document),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    return [
        (
            _json_path(error.absolute_path),
            str(error.validator),
            _json_path(error.absolute_schema_path),
        )
        for error in violations
    ], None


def validate_inventory_schema(
    inventory: dict[str, Any], schema_path: Path = DEFAULT_SCHEMA
) -> list[str]:
    """Validate the inventory against the committed Draft 2020-12 schema."""

    violations, failure = _json_schema_diagnostics(
        inventory, schema_path, "inventory"
    )
    if failure is not None:
        return [failure]
    return [
        f"schema {path}: {validator} constraint failed at {absolute_schema_path}"
        for path, validator, absolute_schema_path in violations
    ]


def validate_reviewed_record_pins_schema(
    record_pins: dict[str, Any],
    schema_path: Path = DEFAULT_REVIEWED_RECORD_PINS_SCHEMA,
) -> list[str]:
    """Validate the versioned reviewed record-pins contract without exposing values."""

    violations, failure = _json_schema_diagnostics(
        record_pins, schema_path, "reviewed record-pins"
    )
    if failure is not None:
        return [f"[{RECORD_PINS_SCHEMA_ERROR}] {failure}"]
    return [
        f"[{RECORD_PINS_SCHEMA_ERROR}] reviewed record-pins schema {path}: "
        f"{validator} constraint failed at {absolute_schema_path}"
        for path, validator, absolute_schema_path in violations
    ]


def _validate_reviewed_record_pins(
    domain: str,
    record_sets: dict[tuple[str, str], dict[str, Any]],
    record_pins: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    domain_pins = [pin for pin in record_pins if pin.get("domain") == domain]
    for pin in domain_pins:
        pin_id = str(pin["id"])
        record_contract = pin["record"]
        owner = str(record_contract["name"]).lower()
        record_type = str(record_contract["type"]).upper()
        record = record_sets.get((owner, record_type))
        if record is None:
            errors.append(
                f"[{RECORD_PIN_MISSING_ERROR}] {domain}: reviewed pin {pin_id} "
                "record is missing"
            )
            continue
        if record.get("ttl") != record_contract["ttl"]:
            errors.append(
                f"[{RECORD_PIN_TTL_ERROR}] {domain}: reviewed pin {pin_id} TTL mismatch"
            )

        values = _strings(record.get("rrdatas"))
        match = pin["match"]
        mode = match["mode"]
        if mode == "filtered_exact_rrset":
            prefix = str(match["filter_prefix"]).lower()
            actual = {value for value in values if value.lower().startswith(prefix)}
            expected = set(match["rrdatas"])
        elif mode == "exact_rrset":
            actual = set(values)
            expected = set(match["rrdatas"])
        else:
            actual = {
                hashlib.sha256(value.encode("utf-8")).hexdigest() for value in values
            }
            expected = set(match["rrdata_sha256"])
        if actual != expected:
            errors.append(
                f"[{RECORD_PIN_RRDATA_ERROR}] {domain}: reviewed pin {pin_id} "
                "RRdata mismatch"
            )

    expected_dkim_owners = {
        str(pin["record"]["name"]).lower()
        for pin in domain_pins
        if pin.get("purpose") == "google_workspace_dkim"
    }
    if expected_dkim_owners:
        actual_dkim_owners = {
            owner
            for owner, record_type in record_sets
            if record_type == "TXT" and owner.endswith("._domainkey")
        }
        if actual_dkim_owners != expected_dkim_owners:
            errors.append(
                f"[{RECORD_PIN_FAMILY_ERROR}] {domain}: reviewed Workspace DKIM "
                "owner set mismatch"
            )
    return errors


def _dmarc_tags(value: str) -> dict[str, str] | None:
    tags: dict[str, str] = {}
    for item in value.split(";"):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            return None
        name, tag_value = (part.strip().lower() for part in item.split("=", 1))
        if not name or not tag_value or name in tags:
            return None
        tags[name] = tag_value
    return tags


def validate_inventory(
    inventory: dict[str, Any],
    require_ready: set[str] | None = None,
    *,
    record_pins_path: Path = DEFAULT_REVIEWED_RECORD_PINS,
    record_pins_schema_path: Path = DEFAULT_REVIEWED_RECORD_PINS_SCHEMA,
) -> list[str]:
    """Return every portfolio policy violation in stable order."""

    errors = validate_inventory_schema(inventory)
    require_ready = require_ready or set()
    reviewed_record_pins: list[dict[str, Any]] = []
    try:
        record_pins = load_reviewed_record_pins(record_pins_path)
    except InventoryError as exc:
        errors.append(str(exc))
    else:
        record_pins_errors = validate_reviewed_record_pins_schema(
            record_pins, record_pins_schema_path
        )
        errors.extend(record_pins_errors)
        if not record_pins_errors:
            reviewed_record_pins = record_pins["pins"]

    if inventory.get("schema_version") != 3:
        errors.append("schema_version must be 3")
    if inventory.get("registrar") != EXPECTED_REGISTRAR:
        errors.append(f"registrar must be {EXPECTED_REGISTRAR}")
    if inventory.get("authoritative_dns") != EXPECTED_DNS:
        errors.append(f"authoritative_dns must be {EXPECTED_DNS}")
    if inventory.get("cloud_dns_project_id") != EXPECTED_DNS_PROJECT:
        errors.append(f"cloud_dns_project_id must be {EXPECTED_DNS_PROJECT}")
    environment_naming = inventory.get("environment_naming")
    if not isinstance(environment_naming, dict) or any(
        environment_naming.get(field) != value
        for field, value in EXPECTED_ENVIRONMENT_NAMING.items()
    ):
        errors.append(
            "environment_naming must define production, staging, and development "
            "mindclade.ai boundaries without wildcard production records"
        )
        environment_naming = (
            environment_naming if isinstance(environment_naming, dict) else {}
        )
    consumer_alignment_complete = environment_naming.get(
        "consumer_alignment_complete"
    )
    if not isinstance(consumer_alignment_complete, bool):
        errors.append("environment_naming.consumer_alignment_complete must be boolean")
    if environment_naming.get("hostnames") != EXPECTED_HOSTNAMES:
        errors.append(
            "environment_naming.hostnames must define the exact AI, developer, and "
            "Studio hostname matrix for every environment"
        )

    certificate_policy = inventory.get("certificate_policy")
    if not isinstance(certificate_policy, dict):
        errors.append("certificate_policy must be an object")
        certificate_policy = {}
    if certificate_policy.get("owner_repository") != EXPECTED_CERTIFICATE_OWNER:
        errors.append(
            f"certificate owner_repository must be {EXPECTED_CERTIFICATE_OWNER}"
        )
    if certificate_policy.get("service") != EXPECTED_CERTIFICATE_SERVICE:
        errors.append(f"certificate service must be {EXPECTED_CERTIFICATE_SERVICE}")
    if certificate_policy.get("scope") != "regional-per-project":
        errors.append("certificate_policy.scope must be regional-per-project")
    if certificate_policy.get("exact_sans_only") is not True:
        errors.append("certificate_policy.exact_sans_only must be true")
    if certificate_policy.get("wildcard_issuance_allowed") is not False:
        errors.append("certificate_policy.wildcard_issuance_allowed must be false")
    if set(_strings(certificate_policy.get("permitted_issuers"))) != {
        "pki.goog",
        "letsencrypt.org",
    }:
        errors.append(
            "certificate_policy.permitted_issuers must be exactly pki.goog and letsencrypt.org"
        )
    if certificate_policy.get("incident_contact") != "mailto:security@mindclade.com":
        errors.append(
            "certificate_policy.incident_contact must be mailto:security@mindclade.com"
        )
    if certificate_policy.get("certificate_names") != EXPECTED_CERTIFICATE_NAMES:
        errors.append("certificate_policy.certificate_names must match the Gateway contract")
    for field in CERTIFICATE_BLOCKERS:
        if not isinstance(certificate_policy.get(field), bool):
            errors.append(f"certificate_policy.{field} must be boolean")
    if certificate_policy.get("caa_policy_ready") is True and (
        certificate_policy.get("issuer_inventory_complete") is not True
    ):
        errors.append("CAA policy cannot be ready before the issuer inventory is complete")

    migration_window = inventory.get("migration_window")
    if not isinstance(migration_window, dict):
        errors.append("migration_window must be an object")
        migration_window = {}
    migration_status = migration_window.get("status")
    if migration_status not in {"unapproved", "approved"}:
        errors.append("migration_window.status must be unapproved or approved")
    migration_approved = migration_status == "approved"
    if migration_approved:
        change_reference = migration_window.get("change_reference")
        starts_at = _timestamp(migration_window.get("starts_at"))
        ends_at = _timestamp(migration_window.get("ends_at"))
        if not isinstance(change_reference, str) or not CHANGE_REFERENCE.fullmatch(
            change_reference
        ):
            errors.append("approved migration window requires a valid change_reference")
        if starts_at is None or ends_at is None:
            errors.append("approved migration window requires timezone-aware timestamps")
        elif starts_at >= ends_at:
            errors.append("migration window starts_at must precede ends_at")
    elif any(
        migration_window.get(field) is not None
        for field in ("change_reference", "starts_at", "ends_at")
    ):
        errors.append("unapproved migration window must not carry approval details")

    module = inventory.get("module_contract")
    if not isinstance(module, dict):
        errors.append("module_contract must be an object")
        module = {}
    if module.get("repository") != EXPECTED_MODULE_REPOSITORY:
        errors.append(f"module repository must be {EXPECTED_MODULE_REPOSITORY}")
    if module.get("path") != EXPECTED_MODULE_PATH:
        errors.append(f"module path must be {EXPECTED_MODULE_PATH}")
    if module.get("certificate_path") != "infra/terraform/modules/certificate_manager":
        errors.append(
            "module certificate_path must be infra/terraform/modules/certificate_manager"
        )
    module_ref = module.get("ref")
    if not isinstance(module_ref, str) or not SEMVER_REF.fullmatch(module_ref):
        errors.append("module ref must be a full semantic version")
    release_status = module.get("release_status")
    if release_status not in MODULE_RELEASE_STATUSES:
        errors.append("module release_status must be planned or published")
    allowed_types = set(_strings(module.get("allowed_public_record_types")))
    if allowed_types != MODULE_PUBLIC_TYPES:
        errors.append(
            "module allowed_public_record_types must be exactly CAA, MX, NS, and TXT"
        )
    conditional_types = set(
        _strings(module.get("conditionally_allowed_public_record_types"))
    )
    if conditional_types != MODULE_CONDITIONAL_PUBLIC_TYPES:
        errors.append(
            "module conditionally_allowed_public_record_types must be exactly A, AAAA, and CNAME"
        )
    supports_name_override = module.get("supports_record_name_override")
    if not isinstance(supports_name_override, bool):
        errors.append("module supports_record_name_override must be boolean")

    domains = inventory.get("domains")
    if not isinstance(domains, list):
        return errors + ["domains must be a list"]
    by_name: dict[str, dict[str, Any]] = {}
    for index, domain in enumerate(domains):
        if not isinstance(domain, dict):
            errors.append(f"domains[{index}] must be an object")
            continue
        name = domain.get("domain")
        if not isinstance(name, str):
            errors.append(f"domains[{index}].domain must be a string")
            continue
        if name in by_name:
            errors.append(f"duplicate domain: {name}")
        by_name[name] = domain

    missing = set(EXPECTED_DOMAINS) - set(by_name)
    extra = set(by_name) - set(EXPECTED_DOMAINS)
    if missing:
        errors.append(f"missing domains: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"unexpected domains: {', '.join(sorted(extra))}")
    unknown_required = require_ready - set(EXPECTED_DOMAINS)
    if unknown_required:
        errors.append(
            f"cannot require unknown domains: {', '.join(sorted(unknown_required))}"
        )

    for name in sorted(set(EXPECTED_DOMAINS) & set(by_name)):
        domain = by_name[name]
        expected_role, expected_mail = EXPECTED_DOMAINS[name]
        prefix = name
        if domain.get("role") != expected_role:
            errors.append(f"{prefix}: role must be {expected_role}")
        if domain.get("mail_policy") != expected_mail:
            errors.append(f"{prefix}: mail_policy must be {expected_mail}")
        if domain.get("dnssec_required") is not True:
            errors.append(f"{prefix}: dnssec_required must be true")
        certificate_serving = domain.get("certificate_serving")
        if certificate_serving is not (name in CERTIFICATE_DOMAINS):
            errors.append(
                f"{prefix}: certificate_serving must be {str(name in CERTIFICATE_DOMAINS).lower()}"
            )
        expected_dynamic = ["CNAME"] if name in CERTIFICATE_DOMAINS else []
        if domain.get("dynamic_record_types") != expected_dynamic:
            errors.append(
                f"{prefix}: dynamic_record_types must be {expected_dynamic}; generated "
                "Certificate Manager CNAMEs are not static inventory records"
            )
        allowlist_value = domain.get("public_record_allowlist")
        if not isinstance(allowlist_value, list) or not all(
            isinstance(item, str) and item for item in allowlist_value
        ):
            errors.append(f"{prefix}: public_record_allowlist must be a string list")
            allowlist: set[str] = set()
        else:
            allowlist = set(allowlist_value)
            if len(allowlist) != len(allowlist_value):
                errors.append(f"{prefix}: public_record_allowlist entries must be unique")
        expected_allowlist = APPROVED_PUBLIC_RECORD_ALLOWLISTS[name]
        if allowlist != expected_allowlist:
            errors.append(
                f"{prefix}: public_record_allowlist must be exactly "
                f"{sorted(expected_allowlist)}"
            )

        complete = domain.get("inventory_complete")
        ready = domain.get("delegation_ready")
        blockers = domain.get("activation_blockers")
        if not isinstance(complete, bool):
            errors.append(f"{prefix}: inventory_complete must be boolean")
        if not isinstance(ready, bool):
            errors.append(f"{prefix}: delegation_ready must be boolean")
        if not isinstance(blockers, list) or not all(
            isinstance(blocker, str) and BLOCKER.fullmatch(blocker)
            for blocker in blockers
        ):
            errors.append(
                f"{prefix}: activation_blockers must be normalized kebab-case strings"
            )
            blockers = []
        if len(blockers) != len(set(blockers)):
            errors.append(f"{prefix}: activation blockers must be unique")
        if ready and complete is not True:
            errors.append(f"{prefix}: delegation_ready requires a complete inventory")
        if ready and blockers:
            errors.append(f"{prefix}: delegation_ready requires no activation blockers")
        if ready and release_status != "published":
            errors.append(f"{prefix}: delegation_ready requires a published module ref")
        if ready is False and not blockers:
            errors.append(f"{prefix}: a blocked delegation must state its blockers")
        if release_status == "planned" and MODULE_RELEASE_BLOCKER not in blockers:
            errors.append(
                f"{prefix}: planned module ref requires the {MODULE_RELEASE_BLOCKER} blocker"
            )
        if release_status == "published" and MODULE_RELEASE_BLOCKER in blockers:
            errors.append(f"{prefix}: remove the stale module-release activation blocker")
        if not migration_approved and MIGRATION_WINDOW_BLOCKER not in blockers:
            errors.append(
                f"{prefix}: unapproved migration requires the "
                f"{MIGRATION_WINDOW_BLOCKER} blocker"
            )
        if migration_approved and MIGRATION_WINDOW_BLOCKER in blockers:
            errors.append(f"{prefix}: remove the stale migration-window blocker")
        if name == "mindclade.ai":
            if (
                consumer_alignment_complete is not True
                and ENVIRONMENT_ALIGNMENT_BLOCKER not in blockers
            ):
                errors.append(
                    f"{prefix}: incomplete consumer naming alignment requires the "
                    f"{ENVIRONMENT_ALIGNMENT_BLOCKER} blocker"
                )
            if (
                consumer_alignment_complete is True
                and ENVIRONMENT_ALIGNMENT_BLOCKER in blockers
            ):
                errors.append(f"{prefix}: remove the stale hostname-alignment blocker")
        if name in CERTIFICATE_DOMAINS:
            for field, blocker in CERTIFICATE_BLOCKERS.items():
                if certificate_policy.get(field) is not True and blocker not in blockers:
                    errors.append(
                        f"{prefix}: incomplete certificate policy requires the {blocker} blocker"
                    )
                if certificate_policy.get(field) is True and blocker in blockers:
                    errors.append(
                        f"{prefix}: remove the stale {field.replace('_', '-')} blocker"
                    )
        if name in require_ready and ready is not True:
            errors.append(f"{prefix}: delegation is not ready")

        records = domain.get("records")
        if not isinstance(records, list):
            errors.append(f"{prefix}: records must be a list")
            continue
        seen: set[tuple[str, str]] = set()
        record_key_types: dict[str, list[str]] = {}
        for record_index, record in enumerate(records):
            record_prefix = f"{prefix}: records[{record_index}]"
            if not isinstance(record, dict):
                errors.append(f"{record_prefix} must be an object")
                continue
            owner = record.get("name")
            record_type = record.get("type")
            ttl = record.get("ttl")
            rrdatas = record.get("rrdatas")
            if not isinstance(owner, str):
                errors.append(f"{record_prefix} has an invalid relative owner name")
                continue
            if "*" in owner:
                errors.append(f"{record_prefix} may not use a wildcard owner")
            if not RECORD_NAME.fullmatch(owner):
                errors.append(f"{record_prefix} has an invalid relative owner name")
                continue
            if not isinstance(record_type, str):
                errors.append(f"{record_prefix}.type must be a string")
                continue
            record_type = record_type.upper()
            if record_type not in MODULE_SUPPORTED_PUBLIC_TYPES:
                errors.append(
                    f"{record_prefix}: public type {record_type} is not supported by the DNS module"
                )
            record_key = _record_map_key(owner, record_type)
            record_key_types.setdefault(record_key, []).append(record_type)
            if (
                record_type in MODULE_CONDITIONAL_PUBLIC_TYPES
                and record_key not in allowlist
            ):
                errors.append(
                    f"{record_prefix}: public {record_type} record key {record_key} "
                    "requires exact public_record_allowlist membership"
                )
            approved_record = APPROVED_PUBLIC_RECORDS.get(name, {}).get(record_key)
            if record_type in MODULE_CONDITIONAL_PUBLIC_TYPES and approved_record:
                actual_record = (
                    owner.lower(),
                    record_type,
                    ttl,
                    tuple(sorted(rrdatas))
                    if isinstance(rrdatas, list)
                    and all(isinstance(value, str) for value in rrdatas)
                    else (),
                )
                if actual_record != approved_record:
                    errors.append(
                        f"{record_prefix}: allowlisted public record {record_key} must "
                        "match the exact reviewed incumbent Squarespace record"
                    )
            if record_type == "NS" and owner == "@":
                errors.append(f"{record_prefix}: Cloud DNS owns the apex NS record set")
            if owner.lower().startswith("_acme-challenge"):
                errors.append(
                    f"{record_prefix}: Certificate Manager authorization records are dynamically owned outside the static inventory"
                )
            if not isinstance(ttl, int) or isinstance(ttl, bool) or not 30 <= ttl <= 86400:
                errors.append(f"{record_prefix}.ttl must be an integer from 30 to 86400")
            if not isinstance(rrdatas, list) or not rrdatas or not all(
                isinstance(value, str) and value.strip() for value in rrdatas
            ):
                errors.append(f"{record_prefix}.rrdatas must contain non-empty strings")
            key = (owner.lower(), record_type)
            if key in seen:
                errors.append(f"{record_prefix}: duplicate record set {owner}/{record_type}")
            seen.add(key)

        for allowlist_entry in sorted(allowlist):
            matching_types = record_key_types.get(allowlist_entry, [])
            if (
                len(matching_types) != 1
                or matching_types[0] not in MODULE_CONDITIONAL_PUBLIC_TYPES
            ):
                errors.append(
                    f"{prefix}: public_record_allowlist entry {allowlist_entry} must "
                    "match exactly one A, AAAA, or CNAME record"
                )

        record_sets = _record_sets(domain)
        apex_txt = _txt_values(record_sets, "@")
        errors.extend(
            _validate_reviewed_record_pins(
                name, record_sets, reviewed_record_pins
            )
        )
        if name in CERTIFICATE_DOMAINS:
            apex_caa = record_sets.get(("@", "CAA"))
            if apex_caa is None:
                errors.append(f"{prefix}: certificate-serving domains require planned apex CAA")
            elif set(_strings(apex_caa.get("rrdatas"))) != EXPECTED_CAA:
                errors.append(
                    f"{prefix}: apex CAA must permit pki.goog and letsencrypt.org, "
                    "forbid wildcards, and carry the security iodef contact"
                )
        if expected_mail == "no-mail":
            null_mx = record_sets.get(("@", "MX"), {}).get("rrdatas")
            if null_mx != ["0 ."]:
                errors.append(f"{prefix}: no-mail policy requires apex null MX '0 .'")
            spf = [
                value
                for value in apex_txt
                if value.lower().startswith("v=spf1 ")
            ]
            if spf != ["v=spf1 -all"]:
                errors.append(f"{prefix}: no-mail policy requires apex SPF 'v=spf1 -all'")
            dmarc = _txt_values(record_sets, "_dmarc")
            dmarc_tags = _dmarc_tags(dmarc[0]) if len(dmarc) == 1 else None
            required_dmarc_tags = {
                "v": "dmarc1",
                "p": "reject",
                "sp": "reject",
                "adkim": "s",
                "aspf": "s",
            }
            if dmarc_tags != required_dmarc_tags:
                errors.append(
                    f"{prefix}: no-mail policy requires exact DMARC p=reject, "
                    "sp=reject, adkim=s, and aspf=s"
                )

        if expected_mail == "google-workspace" and ready:
            spf = [value for value in apex_txt if value.lower().startswith("v=spf1 ")]
            if spf != [FINAL_WORKSPACE_SPF]:
                errors.append(
                    f"{prefix}: Workspace readiness requires final Google-only hard-fail SPF"
                )
            dmarc = _txt_values(record_sets, "_dmarc")
            if dmarc != [FINAL_WORKSPACE_DMARC]:
                errors.append(
                    f"{prefix}: Workspace readiness requires final DMARC reject policy"
                )

        owners: dict[str, set[str]] = {}
        for owner, record_type in seen:
            owners.setdefault(owner, set()).add(record_type)
        needs_override = any(len(types) > 1 for types in owners.values())
        override_blocker = "dns-module-record-name-override-not-released"
        if supports_name_override is True and override_blocker in blockers:
            errors.append(f"{prefix}: remove the stale released-module activation blocker")
        if needs_override and supports_name_override is False:
            if override_blocker not in blockers:
                errors.append(
                    f"{prefix}: multiple record types on one owner require the unreleased name override and its activation blocker"
                )
            if ready:
                errors.append(
                    f"{prefix}: delegation cannot be ready until a released module supports record name overrides"
                )

    return sorted(set(errors))


def _matching_delimiter(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
    raise InventoryError(f"unclosed {opening} block")


def _assignment_object(text: str, name: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=\s*\{{", text)
    if not match:
        raise InventoryError(f"missing {name} object")
    start = text.index("{", match.start())
    end = _matching_delimiter(text, start, "{", "}")
    return text[start + 1 : end]


def _hcl_string(block: str, field: str, required: bool = True) -> str | None:
    match = re.search(
        rf'(?m)^\s*{re.escape(field)}\s*=\s*("(?:\\.|[^"\\])*")\s*$', block
    )
    if not match:
        if required:
            raise InventoryError(f"missing string field {field}")
        return None
    return json.loads(match.group(1))


def _hcl_bool(block: str, field: str) -> bool:
    match = re.search(rf"(?m)^\s*{re.escape(field)}\s*=\s*(true|false)\s*$", block)
    if not match:
        raise InventoryError(f"missing boolean field {field}")
    return match.group(1) == "true"


def _hcl_int(block: str, field: str) -> int:
    match = re.search(rf"(?m)^\s*{re.escape(field)}\s*=\s*([0-9]+)\s*$", block)
    if not match:
        raise InventoryError(f"missing integer field {field}")
    return int(match.group(1))


def _hcl_list(block: str, field: str) -> list[str]:
    match = re.search(rf"(?m)^\s*{re.escape(field)}\s*=\s*\[", block)
    if not match:
        raise InventoryError(f"missing list field {field}")
    start = block.index("[", match.start())
    end = _matching_delimiter(block, start, "[", "]")
    try:
        values = json.loads(block[start : end + 1])
    except json.JSONDecodeError as exc:
        raise InventoryError(f"invalid string list field {field}: {exc}") from exc
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise InventoryError(f"{field} must be a string list")
    return values


def _top_level_record_blocks(records: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r'(?m)^\s*(?P<key>"(?:\\.|[^"\\])*"|[A-Za-z0-9_@.-]+)\s*=\s*\{'
    )
    result: list[tuple[str, str]] = []
    position = 0
    while position < len(records):
        match = pattern.search(records, position)
        if not match:
            break
        prefix = records[: match.start()]
        try:
            depth = prefix.count("{") - prefix.count("}")
        except ValueError:
            depth = 1
        if depth != 0:
            position = match.end()
            continue
        key_token = match.group("key")
        key = json.loads(key_token) if key_token.startswith('"') else key_token
        start = records.index("{", match.start())
        end = _matching_delimiter(records, start, "{", "}")
        result.append((key, records[start + 1 : end]))
        position = end + 1
    return result


def _normalize_hcl_rdata(record_type: str, value: str) -> str:
    value = value.strip()
    if record_type == "TXT" and len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def parse_live_zone(path: Path) -> dict[str, Any]:
    """Parse the intentionally small Terragrunt zone shape without an HCL dependency."""

    text = path.read_text(encoding="utf-8")
    version_match = re.search(r'(?m)^\s*module_version\s*=\s*"([^"]+)"\s*$', text)
    if not version_match:
        raise InventoryError("missing module_version")
    canonical_inventory = (
        'contracts/dns-domain-inventory.json' in text
        and bool(re.search(r'(?m)^\s*records\s*=\s*local\.records\s*$', text))
    )
    zones = _assignment_object(text, "zones")
    zone_blocks = _top_level_record_blocks(zones)
    if len(zone_blocks) != 1:
        raise InventoryError("each public-zone unit must own exactly one zone")
    _zone_key, zone = zone_blocks[0]
    canonical_allowlist = bool(
        re.search(
            r"(?m)^\s*public_record_allowlist\s*=\s*"
            r"local\.domain\.public_record_allowlist\s*$",
            zone,
        )
    )
    dns_name = _hcl_string(zone, "dns_name", required=False)
    domain_attribute = "dns_name"
    if dns_name is None:
        dns_name = _hcl_string(zone, "domain")
        domain_attribute = "domain"
    assert dns_name is not None
    records: list[dict[str, Any]] = []
    if canonical_inventory:
        selected_domain = re.search(
            r'domain\.domain\s*==\s*"([^"]+)"', text
        )
        if selected_domain is None or selected_domain.group(1) != dns_name.rstrip("."):
            raise InventoryError(
                "canonical inventory selector must match the unit's dns_name"
            )
    else:
        records_block = _assignment_object(zone, "records")
        for record_key, record in _top_level_record_blocks(records_block):
            owner = _hcl_string(record, "name", required=False)
            record_type = _hcl_string(record, "type")
            assert record_type is not None
            rrdatas = [
                _normalize_hcl_rdata(record_type.upper(), value)
                for value in _hcl_list(record, "rrdatas")
            ]
            records.append(
                {
                    "name": record_key if owner is None else owner,
                    "type": record_type.upper(),
                    "ttl": _hcl_int(record, "ttl"),
                    "rrdatas": rrdatas,
                }
            )
    return {
        "module_ref": version_match.group(1),
        "domain": dns_name.rstrip("."),
        "domain_attribute": domain_attribute,
        "visibility": _hcl_string(zone, "visibility"),
        "dnssec": _hcl_bool(zone, "dnssec"),
        "declares_deletion_protection": bool(
            re.search(r"(?m)^\s*deletion_protection\s*=", zone)
        ),
        "records": records,
        "canonical_inventory": canonical_inventory,
        "canonical_allowlist": canonical_allowlist,
    }


def _normalized_record(record: dict[str, Any]) -> tuple[str, str, int, tuple[str, ...]]:
    return (
        str(record.get("name", "")).lower(),
        str(record.get("type", "")).upper(),
        int(record.get("ttl", 0)),
        tuple(sorted(str(value) for value in record.get("rrdatas", []))),
    )


def validate_live_parity(
    inventory: dict[str, Any], public_zones: Path = PUBLIC_ZONES
) -> list[str]:
    """Verify that the normalized inventory matches every live public-zone unit."""

    errors: list[str] = []
    module = inventory.get("module_contract", {})
    expected_ref = module.get("ref") if isinstance(module, dict) else None
    domains = inventory.get("domains", [])
    if not isinstance(domains, list):
        return ["cannot validate live parity without a domains list"]
    inventory_domains = {
        domain.get("domain"): domain
        for domain in domains
        if isinstance(domain, dict) and isinstance(domain.get("domain"), str)
    }
    for domain in sorted(EXPECTED_DOMAINS):
        path = public_zones / domain.replace(".", "-") / "terragrunt.hcl"
        try:
            live = parse_live_zone(path)
        except (OSError, InventoryError, ValueError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        if live["domain"] != domain:
            errors.append(f"{domain}: live unit declares {live['domain']}")
        expected_domain = inventory_domains.get(domain, {})
        blockers = expected_domain.get("activation_blockers", [])
        ready = expected_domain.get("delegation_ready") is True
        interface_blocker = "dns-live-zone-interface-not-aligned"
        if live["domain_attribute"] != "dns_name" and (
            ready or interface_blocker not in blockers
        ):
            errors.append(
                f"{domain}: live zone must use the released module's dns_name attribute"
            )
        if live["module_ref"] != expected_ref:
            errors.append(
                f"{domain}: live module ref {live['module_ref']} does not match inventory {expected_ref}"
            )
        if live["visibility"] != "public":
            errors.append(f"{domain}: live zone visibility must be public")
        if live["dnssec"] is not True:
            errors.append(f"{domain}: live zone must enable DNSSEC")
        if live["declares_deletion_protection"]:
            errors.append(
                f"{domain}: deletion_protection is not a DNS module input; "
                "zone deletion is protected inside the module"
            )
        if live["canonical_inventory"] is not True:
            errors.append(
                f"{domain}: public-zone records must be derived from the canonical inventory"
            )
        if live["canonical_allowlist"] is not True:
            errors.append(
                f"{domain}: public record allowlist must be derived from the canonical inventory"
            )
        # Static record parity is guaranteed by direct evaluation of local.domain.records;
        # retaining a second parsed representation here would recreate the duplication this
        # contract removes.
    return sorted(set(errors))


def validate_shared_dns_hub_interface(path: Path = SHARED_DNS_HUB) -> list[str]:
    """Reject the legacy zone attribute before Terraform silently drops it."""

    try:
        text = path.read_text(encoding="utf-8")
        zones = _assignment_object(text, "zones")
        zone_blocks = _top_level_record_blocks(zones)
    except (OSError, InventoryError, ValueError) as exc:
        return [f"{path.relative_to(ROOT)}: {exc}"]

    errors: list[str] = []
    if not zone_blocks:
        errors.append(f"{path.relative_to(ROOT)}: shared DNS hub declares no zones")
    for zone_key, zone in zone_blocks:
        legacy_domain = _hcl_string(zone, "domain", required=False)
        dns_name = _hcl_string(zone, "dns_name", required=False)
        if legacy_domain is not None:
            errors.append(
                f"{path.relative_to(ROOT)}: {zone_key} uses legacy domain; use dns_name"
            )
        if dns_name is None:
            errors.append(
                f"{path.relative_to(ROOT)}: {zone_key} must declare dns_name"
            )
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", nargs="?", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument(
        "--require-ready",
        action="append",
        default=[],
        metavar="DOMAIN",
        help="fail unless DOMAIN is explicitly delegation-ready; repeatable",
    )
    parser.add_argument(
        "--skip-live-parity",
        action="store_true",
        help="validate a standalone inventory without reading this repository's live units",
    )
    args = parser.parse_args()
    try:
        inventory = load_inventory(args.inventory)
    except InventoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    errors = validate_inventory(inventory, set(args.require_ready))
    if not args.skip_live_parity:
        errors.extend(validate_live_parity(inventory))
        errors.extend(validate_shared_dns_hub_interface())
    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    ready = sorted(
        domain["domain"]
        for domain in inventory["domains"]
        if domain.get("delegation_ready") is True
    )
    pending = sorted(set(EXPECTED_DOMAINS) - set(ready))
    print(
        "DNS portfolio validation passed; "
        f"delegation-ready={','.join(ready) or 'none'}; "
        f"blocked={','.join(pending) or 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
