#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Generate the human-readable DNS portfolio projection from the canonical JSON contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from validate_dns_portfolio import DEFAULT_INVENTORY, InventoryError, load_inventory


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "3-networks/shared/public-zones/domains.yaml"


def _scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    text = str(value)
    if text == "" or text.strip() != text or any(char in text for char in ":#[]{}\"'"):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def render(inventory: dict[str, Any]) -> str:
    """Return a deterministic, deliberately small YAML policy projection."""

    naming = inventory["environment_naming"]
    certificates = inventory["certificate_policy"]
    lines = [
        "# Copyright © 2026 Mindclade, LLC. All Rights Reserved.",
        "# Mindclade Proprietary and Confidential.",
        "# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary",
        "",
        "# GENERATED from contracts/dns-domain-inventory.json. DO NOT EDIT.",
        "---",
        f"schema_version: {inventory['schema_version']}",
        f"registrar: {_scalar(inventory['registrar'])}",
        f"authoritative_dns: {_scalar(inventory['authoritative_dns'])}",
        f"cloud_dns_project_id: {_scalar(inventory['cloud_dns_project_id'])}",
        "zones:",
    ]
    for domain in inventory["domains"]:
        lines.extend(
            [
                f"  - domain: {_scalar(domain['domain'])}",
                f"    role: {_scalar(domain['role'])}",
                "    public_record_allowlist: "
                f"[{', '.join(domain['public_record_allowlist'])}]",
                "    dnssec: required",
                f"    certificate_serving: {_scalar(domain['certificate_serving'])}",
                f"    delegation_ready: {_scalar(domain['delegation_ready'])}",
            ]
        )
    mail_enabled = [d["domain"] for d in inventory["domains"] if d["mail_policy"] != "no-mail"]
    no_mail = [d["domain"] for d in inventory["domains"] if d["mail_policy"] == "no-mail"]
    lines.extend(
        [
            "mail_policy:",
            f"  mail_enabled: [{', '.join(mail_enabled)}]",
            f"  no_mail_by_default: [{', '.join(no_mail)}]",
            "change_policy:",
            "  apex_records: terraform-reviewed",
            "  wildcard_dns: forbidden",
            "  external_dns_scope: delegated-subzones-only",
            "environment_naming:",
            f"  production: {_scalar(naming['production'])}",
            f"  staging: {_scalar(naming['staging'])}",
            f"  development: {_scalar(naming['development'])}",
            f"  consumer_alignment_complete: {_scalar(naming['consumer_alignment_complete'])}",
            "  hostnames:",
        ]
    )
    for environment in ("development", "staging", "production"):
        lines.append(f"    {environment}:")
        for plane in ("ai", "developer", "studio"):
            values = ", ".join(naming["hostnames"][environment][plane])
            lines.append(f"      {plane}: [{values}]")
    lines.extend(
        [
            "certificate_policy:",
            f"  owner_repository: {_scalar(certificates['owner_repository'])}",
            f"  service: {_scalar(certificates['service'])}",
            f"  scope: {_scalar(certificates['scope'])}",
            f"  exact_sans_only: {_scalar(certificates['exact_sans_only'])}",
            f"  wildcard_issuance_allowed: {_scalar(certificates['wildcard_issuance_allowed'])}",
            f"  permitted_issuers: [{', '.join(certificates['permitted_issuers'])}]",
            f"  dns_authorizations_ready: {_scalar(certificates['dns_authorizations_ready'])}",
            f"  caa_policy_ready: {_scalar(certificates['caa_policy_ready'])}",
            f"migration_window: {_scalar(inventory['migration_window']['status'])}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        expected = render(load_inventory(args.inventory))
    except (InventoryError, KeyError, TypeError) as exc:
        print(f"ERROR: cannot generate DNS projection: {exc}", file=sys.stderr)
        return 1
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(expected, encoding="utf-8")
        print(f"generated {args.output}")
        return 0
    try:
        actual = args.output.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read generated projection {args.output}: {exc}", file=sys.stderr)
        return 1
    if actual != expected:
        print(
            f"ERROR: {args.output} is stale; run scripts/generate_dns_domains.py --write",
            file=sys.stderr,
        )
        return 1
    print(f"DNS projection is current: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
