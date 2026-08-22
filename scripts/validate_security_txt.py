#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Generate and validate RFC 9116 security.txt artifacts for the domain portfolio."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

EXPECTED_DOMAINS = {"mindclade.com", "mindclade.ai", "mindclade.dev", "mindclade.studio"}
OUTPUT_ROOT = Path("3-networks/shared/security-txt")
BLOCKER_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SecurityTxtError(ValueError):
    """The security.txt contract or generated artifact is unsafe or incomplete."""


def load_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecurityTxtError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SecurityTxtError("security.txt contract must be an object")
    expected = {
        "schemaVersion",
        "contact",
        "policy",
        "preferredLanguages",
        "expires",
        "domains",
        "publication",
    }
    if set(value) != expected:
        raise SecurityTxtError(f"contract keys must be exactly {sorted(expected)}")
    return value


def _timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SecurityTxtError("Expires must be a UTC RFC 3339 timestamp ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SecurityTxtError("Expires must be a valid RFC 3339 timestamp") from exc
    if parsed.microsecond:
        raise SecurityTxtError("Expires must not contain fractional seconds")
    return parsed


def validate_contract(contract: dict[str, Any], today: dt.date) -> None:
    if contract["schemaVersion"] != 1:
        raise SecurityTxtError("schemaVersion must be 1")
    if contract["contact"] != "mailto:security@mindclade.com":
        raise SecurityTxtError("Contact must be the canonical security mailbox")
    if contract["policy"] != "https://mindclade.com/security":
        raise SecurityTxtError("Policy must be the canonical public HTTPS policy URL")
    if contract["preferredLanguages"] != ["en"]:
        raise SecurityTxtError("Preferred-Languages must be exactly en")
    domains = contract["domains"]
    if not isinstance(domains, list) or set(domains) != EXPECTED_DOMAINS or len(domains) != 4:
        raise SecurityTxtError("domains must contain each controlled apex exactly once")
    expires = _timestamp(contract["expires"])
    start = dt.datetime.combine(today, dt.time(), tzinfo=dt.timezone.utc)
    remaining = expires - start
    if remaining < dt.timedelta(days=30):
        raise SecurityTxtError("Expires is inside the 30-day renewal window")
    if remaining > dt.timedelta(days=366):
        raise SecurityTxtError("Expires must be no more than 366 days in the future")
    publication = contract["publication"]
    if not isinstance(publication, dict) or set(publication) != {
        "status",
        "mechanism",
        "activationBlockers",
        "connectedEvidence",
    }:
        raise SecurityTxtError("publication contract is malformed")
    if publication["mechanism"] != "https-origin-owned-by-platform":
        raise SecurityTxtError("publication mechanism must preserve the platform origin boundary")
    blockers = publication["activationBlockers"]
    if not isinstance(blockers, list) or len(blockers) != len(set(blockers)) or not all(
        isinstance(item, str) and BLOCKER_RE.fullmatch(item) for item in blockers
    ):
        raise SecurityTxtError("activationBlockers must be unique kebab-case identifiers")
    if publication["status"] == "blocked":
        if not blockers or publication["connectedEvidence"] is not None:
            raise SecurityTxtError("blocked publication requires blockers and no connected evidence")
    elif publication["status"] == "published":
        evidence = publication["connectedEvidence"]
        if blockers or not isinstance(evidence, dict) or set(evidence) != {
            "verifiedAt",
            "evidenceUrl",
        }:
            raise SecurityTxtError("published status requires blocker-free connected evidence")
        _timestamp(evidence["verifiedAt"])
        if not str(evidence["evidenceUrl"]).startswith("https://"):
            raise SecurityTxtError("connected evidence must use HTTPS")
    else:
        raise SecurityTxtError("publication status must be blocked or published")


def render(contract: dict[str, Any], domain: str) -> str:
    return "\n".join(
        [
            f"Contact: {contract['contact']}",
            f"Expires: {contract['expires']}",
            f"Preferred-Languages: {','.join(contract['preferredLanguages'])}",
            f"Canonical: https://{domain}/.well-known/security.txt",
            f"Policy: {contract['policy']}",
            "",
        ]
    )


def output_path(root: Path, domain: str) -> Path:
    return root / OUTPUT_ROOT / domain / ".well-known" / "security.txt"


def atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
    temporary.replace(path)


def validate_outputs(contract: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    for domain in sorted(EXPECTED_DOMAINS):
        path = output_path(root, domain)
        expected = render(contract, domain)
        if not path.is_file():
            errors.append(f"missing generated security.txt: {path.relative_to(root)}")
        elif path.read_text(encoding="utf-8") != expected:
            errors.append(f"stale generated security.txt: {path.relative_to(root)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--contract", type=Path, default=Path("contracts/security-txt.json"))
    parser.add_argument("--today", type=dt.date.fromisoformat, default=dt.datetime.now(dt.timezone.utc).date())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    contract_path = args.contract if args.contract.is_absolute() else root / args.contract
    try:
        contract = load_contract(contract_path)
        validate_contract(contract, args.today)
        if args.write:
            for domain in sorted(EXPECTED_DOMAINS):
                atomic_write(output_path(root, domain), render(contract, domain))
        errors = validate_outputs(contract, root)
        if errors:
            raise SecurityTxtError("; ".join(errors))
        status = contract["publication"]["status"]
        print(f"security.txt source artifacts validated: {len(EXPECTED_DOMAINS)} domains; publication={status}")
    except (OSError, UnicodeDecodeError, SecurityTxtError) as exc:
        print(f"security.txt validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
