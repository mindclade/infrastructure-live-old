#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Build and validate the applied bootstrap account handoff."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

HANDOFF_CONTRACT_VERSION = 1
BOOTSTRAP_PLATFORM_CONTRACT_VERSION = "1.6.0"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts/bootstrap-account-handoff.schema.json"
)
HANDOFF_STATE_BUCKETS = {
    "development": "TFSTATE_BUCKET_DEVELOPMENT",
    "staging": "TFSTATE_BUCKET_STAGING",
    "production": "TFSTATE_BUCKET_PRODUCTION",
}
HANDOFF_SERVICE_ACCOUNTS = {
    "plan": "SA_TF_LIVE_PLAN",
    "foundation": "SA_TF_LIVE_APPLY_FOUNDATION",
    "development": "SA_TF_LIVE_APPLY_DEVELOPMENT",
    "staging": "SA_TF_LIVE_APPLY_STAGING",
    "production": "SA_TF_LIVE_APPLY_PRODUCTION",
}


def bootstrap_source_commit(root: Path) -> str:
    """Return the exact clean bootstrap source commit used to read applied output."""

    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise ValueError("bootstrap checkout has changes or untracked files")
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("bootstrap checkout does not resolve to one full commit SHA")
    return commit


def build_account_handoff(
    contract: dict[str, Any], values: dict[str, Any], source_commit: str
) -> dict[str, Any]:
    """Create the canonical non-secret record bound to applied platform output."""

    if contract.get("contract_version") != BOOTSTRAP_PLATFORM_CONTRACT_VERSION:
        raise ValueError("bootstrap platform contract version differs")
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("bootstrap source commit is invalid")
    encoded = json.dumps(
        contract, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return {
        "schema_version": HANDOFF_CONTRACT_VERSION,
        "bootstrap_contract_version": BOOTSTRAP_PLATFORM_CONTRACT_VERSION,
        "bootstrap_source_commit": source_commit,
        "platform_contract_sha256": f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        "state_location": values["STATE_LOCATION"],
        "state_buckets": {
            key: values[variable] for key, variable in HANDOFF_STATE_BUCKETS.items()
        },
        "service_accounts": {
            key: values[variable]
            for key, variable in HANDOFF_SERVICE_ACCOUNTS.items()
        },
    }


def handoff_schema_errors(handoff: object) -> list[str]:
    """Validate the handoff without returning record contents in diagnostics."""

    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError:
        return [
            "[ACCOUNT-HANDOFF-DEPENDENCY] bootstrap account handoff validation "
            "requires the pinned jsonschema package"
        ]
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, SchemaError):
        return [
            "[ACCOUNT-HANDOFF-CONTRACT] bootstrap account handoff schema is unavailable"
        ]
    if any(Draft202012Validator(schema).iter_errors(handoff)):
        return [
            "[ACCOUNT-HANDOFF-SCHEMA] bootstrap account handoff violates its schema"
        ]
    return []


def account_handoff_errors(payload: str, values: dict[str, str]) -> list[str]:
    """Bind duplicated runtime variables to one applied bootstrap-output record."""

    try:
        handoff = json.loads(payload)
    except json.JSONDecodeError:
        return ["[ACCOUNT-HANDOFF-JSON] bootstrap account handoff is not valid JSON"]
    required = {
        "schema_version",
        "bootstrap_contract_version",
        "bootstrap_source_commit",
        "platform_contract_sha256",
        "state_location",
        "state_buckets",
        "service_accounts",
    }
    errors = handoff_schema_errors(handoff)
    if not isinstance(handoff, dict) or set(handoff) != required:
        return errors + [
            "[ACCOUNT-HANDOFF-SHAPE] bootstrap account handoff is not exact"
        ]

    if handoff.get("schema_version") != HANDOFF_CONTRACT_VERSION:
        errors.append("[ACCOUNT-HANDOFF-VERSION] bootstrap account handoff version differs")
    if handoff.get("bootstrap_contract_version") != BOOTSTRAP_PLATFORM_CONTRACT_VERSION:
        errors.append("[ACCOUNT-HANDOFF-BOOTSTRAP] bootstrap platform contract version differs")
    source_commit = handoff.get("bootstrap_source_commit")
    if not isinstance(source_commit, str) or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        errors.append("[ACCOUNT-HANDOFF-SOURCE] bootstrap source commit is invalid")
    contract_digest = handoff.get("platform_contract_sha256")
    if not isinstance(contract_digest, str) or re.fullmatch(
        r"sha256:[0-9a-f]{64}", contract_digest
    ) is None:
        errors.append("[ACCOUNT-HANDOFF-DIGEST] bootstrap output digest is invalid")
    if handoff.get("state_location") != values["STATE_LOCATION"]:
        errors.append("[ACCOUNT-HANDOFF-MISMATCH] STATE_LOCATION differs from bootstrap output")

    for section, mapping in (
        ("state_buckets", HANDOFF_STATE_BUCKETS),
        ("service_accounts", HANDOFF_SERVICE_ACCOUNTS),
    ):
        observed = handoff.get(section)
        if not isinstance(observed, dict) or set(observed) != set(mapping):
            errors.append(f"[ACCOUNT-HANDOFF-SHAPE] bootstrap {section} inventory is not exact")
            continue
        for key, variable in mapping.items():
            if observed[key] != values[variable]:
                errors.append(
                    f"[ACCOUNT-HANDOFF-MISMATCH] {variable} differs from bootstrap output"
                )
    return errors
