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
EXPECTED_PACKAGE_HASHES_PER_PROVIDER = 2  # darwin_arm64 and linux_amd64

locks = sorted(
    path
    for path in ROOT.rglob(".terraform.lock.hcl")
    if not any(part in {".git", ".terraform", ".terragrunt-cache"} for part in path.parts)
)
missing: list[str] = []
for config in ROOT.rglob("terragrunt.hcl"):
    lock = config.parent / ".terraform.lock.hcl"
    if not lock.is_file():
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
    zip_hashes = re.findall(r'"zh:([0-9a-f]{64})"', body)
    package_hashes = re.findall(r'"h1:([A-Za-z0-9+/]+={0,2})"', body)
    if not version or version.group(1) != EXPECTED_VERSION:
        print(f"{address}: lock version is not {EXPECTED_VERSION}", file=sys.stderr)
        raise SystemExit(1)
    if not constraints or constraints.group(1) != EXPECTED_VERSION:
        print(
            f"{address}: provider constraint is not normalized {EXPECTED_VERSION}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if len(set(zip_hashes)) < 10:
        print(f"{address}: incomplete multi-platform zip checksum set", file=sys.stderr)
        raise SystemExit(1)
    if (
        len(package_hashes) != EXPECTED_PACKAGE_HASHES_PER_PROVIDER
        or len(set(package_hashes)) != EXPECTED_PACKAGE_HASHES_PER_PROVIDER
    ):
        print(
            f"{address}: expected distinct h1 package checksums for "
            "darwin_arm64 and linux_amd64",
            file=sys.stderr,
        )
        raise SystemExit(1)
print(
    "provider lock parity passed: "
    f"{len(locks)} units, {len(entries)} exact providers, "
    "darwin_arm64 + linux_amd64 package hashes, "
    f"{next(iter(digests))}"
)
