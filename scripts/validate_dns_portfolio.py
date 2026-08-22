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


def validate_inventory(
    inventory: dict[str, Any], require_ready: set[str] | None = None
) -> list[str]:
    """Return every portfolio policy violation in stable order."""

    errors: list[str] = []
    require_ready = require_ready or set()

    if inventory.get("schema_version") != 2:
        errors.append("schema_version must be 2")
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
        for record_index, record in enumerate(records):
            record_prefix = f"{prefix}: records[{record_index}]"
            if not isinstance(record, dict):
                errors.append(f"{record_prefix} must be an object")
                continue
            owner = record.get("name")
            record_type = record.get("type")
            ttl = record.get("ttl")
            rrdatas = record.get("rrdatas")
            if not isinstance(owner, str) or not RECORD_NAME.fullmatch(owner):
                errors.append(f"{record_prefix} has an invalid relative owner name")
                continue
            if "*" in owner:
                errors.append(f"{record_prefix} may not use a wildcard owner")
            if not isinstance(record_type, str):
                errors.append(f"{record_prefix}.type must be a string")
                continue
            record_type = record_type.upper()
            if record_type not in MODULE_PUBLIC_TYPES:
                errors.append(
                    f"{record_prefix}: public type {record_type} is not supported by the DNS module"
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

        record_sets = _record_sets(domain)
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
            if _txt_values(record_sets, "@") != ["v=spf1 -all"]:
                errors.append(f"{prefix}: no-mail policy requires apex SPF 'v=spf1 -all'")
            dmarc = _txt_values(record_sets, "_dmarc")
            if len(dmarc) != 1 or not all(
                token in dmarc[0].lower() for token in ("v=dmarc1", "p=reject", "sp=reject")
            ):
                errors.append(
                    f"{prefix}: no-mail policy requires DMARC p=reject and sp=reject"
                )

        if expected_mail == "google-workspace" and ready:
            mx = record_sets.get(("@", "MX"), {}).get("rrdatas", [])
            if not mx or mx == ["0 ."]:
                errors.append(f"{prefix}: Workspace readiness requires a non-null apex MX")
            apex_txt = _txt_values(record_sets, "@")
            spf = [value for value in apex_txt if value.lower().startswith("v=spf1 ")]
            if len(spf) != 1 or "include:_spf.google.com" not in spf[0].lower():
                errors.append(
                    f"{prefix}: Workspace readiness requires one Google-authorizing SPF record"
                )
            verification = [
                value
                for value in apex_txt
                if value.lower().startswith("google-site-verification=")
            ]
            if not verification:
                errors.append(
                    f"{prefix}: Workspace readiness requires a Google verification TXT record"
                )
            dkim = [
                record
                for (owner, record_type), record in record_sets.items()
                if record_type == "TXT" and owner.endswith("._domainkey")
            ]
            if not dkim:
                errors.append(f"{prefix}: Workspace readiness requires a DKIM TXT record")
            dmarc = _txt_values(record_sets, "_dmarc")
            if len(dmarc) != 1 or "v=dmarc1" not in dmarc[0].lower():
                errors.append(f"{prefix}: Workspace readiness requires a DMARC TXT record")

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
