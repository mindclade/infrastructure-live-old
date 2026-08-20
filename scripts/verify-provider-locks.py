#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# MINDCLADE CONFIDENTIAL - PROPRIETARY AND TRADE SECRET
# Copyright (c) 2026 Mindclade. All rights reserved.
"""Verify provider dependency-lock completeness and parity for all live units."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "7.41.0"
EXPECTED_PROVIDERS = {
    "registry.terraform.io/hashicorp/google",
    "registry.terraform.io/hashicorp/google-beta",
}

locks: list[Path] = []
missing: list[str] = []
for config in ROOT.rglob("terragrunt.hcl"):
    lock = config.parent / ".terraform.lock.hcl"
    if lock.is_file():
        locks.append(lock)
    else:
        missing.append(str(lock.relative_to(ROOT)))
if missing:
    print("missing provider locks:\n" + "\n".join(sorted(missing)), file=sys.stderr)
    raise SystemExit(1)
if not locks:
    print("no Terragrunt units found", file=sys.stderr)
    raise SystemExit(1)

digests = {hashlib.sha256(path.read_bytes()).hexdigest() for path in locks}
if len(digests) != 1:
    print(f"provider lock drift: {len(digests)} distinct lockfiles", file=sys.stderr)
    raise SystemExit(1)

sample = locks[0].read_text(encoding="utf-8")
entries = re.findall(r'provider\s+"([^"]+)"\s*\{(.*?)\n\}', sample, flags=re.DOTALL)
addresses = {address for address, _ in entries}
if addresses != EXPECTED_PROVIDERS:
    print(f"provider inventory mismatch: {sorted(addresses)}", file=sys.stderr)
    raise SystemExit(1)
for address, body in entries:
    version = re.search(r'^\s*version\s*=\s*"([^"]+)"', body, flags=re.MULTILINE)
    constraints = re.search(
        r'^\s*constraints\s*=\s*"([^"]+)"', body, flags=re.MULTILINE
    )
    hashes = re.findall(r'"zh:([0-9a-f]{64})"', body)
    if not version or version.group(1) != EXPECTED_VERSION:
        print(f"{address}: lock version is not {EXPECTED_VERSION}", file=sys.stderr)
        raise SystemExit(1)
    if not constraints or constraints.group(1) != f"= {EXPECTED_VERSION}":
        print(f"{address}: provider constraint is not exact", file=sys.stderr)
        raise SystemExit(1)
    if len(set(hashes)) < 10:
        print(f"{address}: incomplete multi-platform zip checksum set", file=sys.stderr)
        raise SystemExit(1)
print(
    "provider lock parity passed: "
    f"{len(locks)} units, {len(entries)} exact providers, {next(iter(digests))}"
)
