#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Validate the fail-closed developer-workstation provisioning-egress contract.

`validate-production-contract.py` already proves that `deny-egress-default` still denies
0.0.0.0/0 in every environment. That is only half of the pressure this contract is under. The
other half is an ALLOW added above the deny to make the workstation finish provisioning: the
deny stays untouched, every existing check stays green, and the estate quietly grows a route to
the public internet. This validator closes that half by requiring every egress allow in
`3-networks` to name a destination the reviewed contract already lists.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/workstation-egress.json"
SCHEMA = ROOT / "contracts/workstation-egress.schema.json"

EXPECTED_BLOCKERS = [
    "artifact-registry-apt-remote-not-expressible",
    "artifact-registry-remote-upstream-unqualified",
    "nix-installer-has-no-internal-source",
    "no-vm-image-build-pipeline",
    "perimeter-egress-contract-untyped",
    "workstation-startup-script-is-not-caller-overridable",
]

# Every alternative that was evaluated and refused stays named. A design that disappears from
# this list is one a later change can re-propose as if it had never been considered.
EXPECTED_REJECTED_DESIGNS = [
    "named-destination-egress-rule",
    "secure-web-proxy",
    "widen-deny-egress-default",
]

REQUIRED_SOURCE_PATHS = (
    "3-networks/development/firewall-baseline/terragrunt.hcl",
    "3-networks/production/firewall-baseline/terragrunt.hcl",
    "3-networks/shared/dns-hub/terragrunt.hcl",
    "3-networks/staging/firewall-baseline/terragrunt.hcl",
    "5-workloads/development/workstation/README.md",
    "5-workloads/development/workstation/terragrunt.hcl",
    "contracts/workstation-egress.json",
    "contracts/workstation-egress.schema.json",
)

# The marker the workstation unit must carry while provisioning cannot complete. Pinning it here
# is what stops the unit's own comment from drifting back into a readiness claim the estate
# cannot support.
BLOCKED_MARKER = "PROVISIONING IS BLOCKED"

# A rule block opens with `name = {` on its own line and closes with `}` at the same indent.
# Nested constructs in these units (`log_config = { ... }`, `allow = [{ ... }]`) are single-line,
# so the closing line at the opening indent is unambiguous.
BLOCK_OPEN = re.compile(r"^(\s*)([a-z][a-z0-9-]*)\s*=\s*\{\s*$")
QUOTED = re.compile(r'"([^"]*)"')


def coded(code: str, message: str) -> str:
    return f"[WSEGRESS-{code}] {message}"


def load_json(path: Path, code: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, [coded(code, f"cannot load {path.name}")]
    if not isinstance(value, dict):
        return None, [coded(code, f"{path.name} root must be an object")]
    return value, []


def schema_errors(document: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from jsonschema.exceptions import SchemaError
    except ImportError:
        return [
            coded(
                "SCHEMA",
                "validation requires the pinned jsonschema package from the CI shell",
            )
        ]

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        return [coded("SCHEMA", "checked-in schema is invalid")]

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(
        validator.iter_errors(document),
        key=lambda item: tuple(str(part) for part in item.path),
    ):
        location = "$" + "".join(f"[{part!r}]" for part in error.path)
        errors.append(coded("SCHEMA", f"{location} violates {error.validator}"))
    return errors


def policy_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = document.get("status")
    blockers = document.get("blockers")
    baseline = document.get("egress_baseline", {})
    selected = document.get("selected_design", {})
    workstation = document.get("workstation", {})

    if status == "blocked" and blockers != EXPECTED_BLOCKERS:
        errors.append(
            coded("POLICY", "blocked lifecycle must retain the exact reviewed blocker set")
        )
    if status == "qualifying" and (
        not blockers or not set(blockers).issubset(EXPECTED_BLOCKERS)
    ):
        errors.append(
            coded("POLICY", "qualifying lifecycle must retain only unresolved reviewed blockers")
        )
    if status in {"qualified", "activated"} and blockers:
        errors.append(coded("POLICY", f"{status} lifecycle cannot retain blockers"))

    rejected = [entry.get("id") for entry in document.get("rejected_designs", [])]
    if sorted(filter(None, rejected)) != EXPECTED_REJECTED_DESIGNS:
        errors.append(
            coded("POLICY", "the reviewed set of rejected designs may not be edited away")
        )

    # The whole point of the selected design is that it adds no destination. A design that does
    # is a different design and needs its own review, not a flag flip in this file.
    if selected.get("adds_egress_destination") is not False:
        errors.append(
            coded("POLICY", "the selected design may not add an egress destination")
        )
    if workstation.get("startup_script_override_available") is not False:
        errors.append(
            coded(
                "POLICY",
                "the module refuses a startup-script metadata override; the contract may not claim one",
            )
        )

    destinations = baseline.get("reviewed_destinations", [])
    for destination in destinations:
        if destination == "0.0.0.0/0":
            errors.append(
                coded("POLICY", "0.0.0.0/0 is never a reviewed egress destination")
            )
            continue
        prefix = destination.rsplit("/", 1)[-1]
        if not prefix.isdigit() or int(prefix) < 8:
            errors.append(
                coded(
                    "POLICY",
                    f"reviewed egress destination is broader than /8: {destination}",
                )
            )
    return sorted(set(errors))


def rule_blocks(text: str) -> dict[str, str]:
    """Return the innermost named blocks that declare a firewall direction.

    Only innermost blocks count. The enclosing `rules = { ... }` map also spans a `direction`
    and an `action = "allow"` and every destination in the file, so treating it as a rule would
    make one broad container look like whatever its narrowest member happens to say first.
    """
    lines = text.splitlines()
    spans: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        opened = BLOCK_OPEN.match(line)
        if not opened:
            continue
        indent, name = opened.group(1), opened.group(2)
        closing = f"{indent}}}"
        for end in range(index + 1, len(lines)):
            if lines[end].rstrip() == closing:
                spans.append((index, end, name))
                break

    blocks: dict[str, str] = {}
    for start, end, name in spans:
        if any(start < other_start and other_end < end for other_start, other_end, _ in spans):
            continue
        body = "\n".join(lines[start + 1 : end])
        # Only firewall rules declare a direction; `firewalls`, `inputs`, and the dependency
        # blocks in the same file do not.
        if re.search(r"\bdirection\s*=", body):
            blocks[name] = body
    return blocks


def destination_ranges(body: str) -> list[str]:
    match = re.search(r"destination_ranges\s*=\s*\[(.*?)\]", body, re.DOTALL)
    if not match:
        return []
    return QUOTED.findall(match.group(1))


def firewall_errors(document: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    baseline = document.get("egress_baseline", {})
    reviewed = set(baseline.get("reviewed_destinations", []))
    deny_rule = baseline.get("deny_rule", "deny-egress-default")
    deny_priority = baseline.get("deny_priority", 65000)
    deny_destination = baseline.get("deny_destination", "0.0.0.0/0")

    for environment in baseline.get("environments", []):
        path = root / f"3-networks/{environment}/firewall-baseline/terragrunt.hcl"
        if not path.is_file():
            errors.append(coded("FIREWALL", f"{environment} firewall baseline is missing"))
            continue
        blocks = rule_blocks(path.read_text(encoding="utf-8"))

        deny = blocks.get(deny_rule)
        if deny is None:
            errors.append(
                coded("FIREWALL", f"{environment} no longer declares {deny_rule}")
            )
        else:
            intact = (
                re.search(r'direction\s+=\s+"EGRESS"', deny)
                and re.search(r'action\s+=\s+"deny"', deny)
                and re.search(rf"priority\s+=\s+{deny_priority}\b", deny)
                and destination_ranges(deny) == [deny_destination]
            )
            if not intact:
                errors.append(
                    coded(
                        "FIREWALL",
                        f"{environment} default egress deny no longer denies {deny_destination} at {deny_priority}",
                    )
                )

        for name, body in blocks.items():
            if name == deny_rule:
                continue
            if not re.search(r'direction\s*=\s*"EGRESS"', body):
                continue
            if not re.search(r'action\s*=\s*"allow"', body):
                continue
            for destination in destination_ranges(body):
                if destination not in reviewed:
                    errors.append(
                        coded(
                            "FIREWALL",
                            f"{environment} egress allow {name} names an unreviewed destination: {destination}",
                        )
                    )
    return sorted(set(errors))


def network_sweep_errors(root: Path = ROOT) -> list[str]:
    """No unit anywhere in 3-networks may allow egress to the whole internet."""
    errors: list[str] = []
    for path in sorted((root / "3-networks").rglob("terragrunt.hcl")):
        for name, body in rule_blocks(path.read_text(encoding="utf-8")).items():
            if not re.search(r'direction\s*=\s*"EGRESS"', body):
                continue
            if not re.search(r'action\s*=\s*"allow"', body):
                continue
            if "0.0.0.0/0" in body or "::/0" in body:
                errors.append(
                    coded(
                        "FIREWALL",
                        f"{path.relative_to(root)} rule {name} allows egress to the whole internet",
                    )
                )
    return sorted(set(errors))


def source_errors(document: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_SOURCE_PATHS:
        if not root.joinpath(relative).is_file():
            errors.append(coded("SOURCE", f"required source file is missing: {relative}"))

    unit = root / "5-workloads/development/workstation/terragrunt.hcl"
    if not unit.is_file():
        return sorted(set(errors))
    text = unit.read_text(encoding="utf-8")

    if "contracts/workstation-egress.json" not in text:
        errors.append(
            coded("SOURCE", "workstation unit does not cite the egress contract it depends on")
        )
    if "create_iap_ssh_firewall_rule = false" not in text:
        errors.append(
            coded("SOURCE", "workstation unit no longer hands its IAP rule to the host project")
        )
    # `var.metadata` refuses module-owned keys, so a caller-side startup script cannot work; it
    # would fail at plan time and read as a module bug rather than the boundary it is.
    if re.search(r'"startup-script"|"shutdown-script"|startup_script\s*=', text):
        errors.append(
            coded("SOURCE", "workstation unit attempts a startup-script override the module refuses")
        )

    status = document.get("status")
    if status != "activated" and BLOCKED_MARKER not in text:
        errors.append(
            coded(
                "SOURCE",
                "workstation unit must state that provisioning is blocked while the contract is not activated",
            )
        )
    if status == "activated" and BLOCKED_MARKER in text:
        errors.append(
            coded("SOURCE", "activated contract contradicts the unit's blocked-provisioning notice")
        )
    return sorted(set(errors))


def validate(
    document: dict[str, Any],
    schema: dict[str, Any],
    *,
    root: Path = ROOT,
) -> list[str]:
    errors = schema_errors(document, schema)
    errors.extend(policy_errors(document))
    errors.extend(firewall_errors(document, root))
    errors.extend(network_sweep_errors(root))
    errors.extend(source_errors(document, root))
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-active",
        action="store_true",
        help="fail unless workstation provisioning is qualified and activated",
    )
    args = parser.parse_args()

    document, errors = load_json(CONTRACT, "LOAD")
    schema, schema_load_errors = load_json(SCHEMA, "LOAD")
    errors.extend(schema_load_errors)
    if document is not None and schema is not None:
        errors.extend(validate(document, schema))
        if args.require_active and document.get("status") != "activated":
            errors.append(coded("ACTIVATION", "workstation provisioning is not activated"))

    if errors:
        for error in sorted(set(errors)):
            print(error, file=sys.stderr)
        return 1
    assert document is not None
    print(f"workstation egress contract passed (lifecycle: {document['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
