#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Validate the exact, expiring upstream Argo Binary Authorization contract."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DIGEST_IMAGE = re.compile(r"[^\s*]+@sha256:[0-9a-f]{64}")
EXPECTED_IMAGE_NAMES = {
    "ghcr.io/dexidp/dex",
    "public.ecr.aws/docker/library/haproxy",
    "public.ecr.aws/docker/library/redis",
    "quay.io/argoproj/argocd",
}
EXPECTED_FIELDS = {
    "image",
    "owner",
    "reason",
    "scope",
    "granted",
    "expires",
    "reviewer",
    "approval",
    "change",
    "removal",
}


def validate_contract(value: Any, today: dt.date | None = None) -> list[str]:
    errors: list[str] = []
    today = today or dt.date.today()
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        return ["exception contract must be a schema_version 1 object"]
    exceptions = value.get("exceptions")
    if not isinstance(exceptions, list):
        return ["exception contract must contain an exceptions list"]
    images: list[str] = []
    for index, exception in enumerate(exceptions):
        label = f"exception[{index}]"
        if not isinstance(exception, dict):
            errors.append(f"{label} must be an object")
            continue
        if set(exception) != EXPECTED_FIELDS:
            errors.append(f"{label} must contain exactly the governed fields")
        image = str(exception.get("image", ""))
        images.append(image)
        if not DIGEST_IMAGE.fullmatch(image):
            errors.append(f"{label} must name one exact digest without wildcards")
        if exception.get("owner") != "@mindclade/platform":
            errors.append(f"{label} owner must be @mindclade/platform")
        if exception.get("reviewer") != "@mindclade/security":
            errors.append(f"{label} reviewer must be @mindclade/security")
        if exception.get("approval") != "required-protected-security-review":
            errors.append(f"{label} must require protected security review")
        if exception.get("change") != "protected-gitops-and-infrastructure-live-pull-requests":
            errors.append(f"{label} must bind both protected pull requests")
        if exception.get("scope") != {
            "component": "argocd-control-plane",
            "environments": ["staging", "production"],
        }:
            errors.append(f"{label} scope must be the staging/production Argo control plane")
        for field in ("reason", "removal"):
            if not str(exception.get(field, "")).strip():
                errors.append(f"{label} missing {field}")
        try:
            granted = dt.date.fromisoformat(str(exception.get("granted", "")))
            expires = dt.date.fromisoformat(str(exception.get("expires", "")))
            if expires < today:
                errors.append(f"{label} is expired")
            if expires < granted or (expires - granted).days > 90:
                errors.append(f"{label} lifetime must be between 0 and 90 days")
        except ValueError:
            errors.append(f"{label} granted/expires must be ISO dates")
    if images != sorted(images) or len(images) != len(set(images)):
        errors.append("exceptions must be unique and image-sorted")
    if {image.split("@", 1)[0] for image in images} != EXPECTED_IMAGE_NAMES:
        errors.append("contract must cover exactly the four approved Argo image names")
    return errors


def gitops_contract_errors(contract_images: set[str], gitops: Path) -> list[str]:
    errors: list[str] = []
    try:
        provenance = json.loads(
            (gitops / "bootstrap/argocd-install.provenance.json").read_text("utf-8")
        )
        provenance_images = {
            f"{str(record['source']).rsplit(':', 1)[0]}@{record['digest']}"
            for record in provenance.get("images") or []
        }
        image_policy_text = (gitops / "image-policy.yaml").read_text("utf-8")
        policy_images = set(
            re.findall(r"(?m)^\s+- image: ([^\s]+@sha256:[0-9a-f]{64})$", image_policy_text)
        )
        gatekeeper_text = (
            gitops / "policy/constraints/require-image-policy.yaml"
        ).read_text("utf-8")
        gatekeeper_images = set(
            re.findall(r"(?m)^\s+- ([^\s]+@sha256:[0-9a-f]{64})$", gatekeeper_text)
        )
        for label, images in (
            ("Argo provenance", provenance_images),
            ("GitOps image policy", policy_images),
            ("Gatekeeper", gatekeeper_images),
        ):
            if images != contract_images:
                errors.append(f"infrastructure exceptions disagree with {label}")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"cannot validate GitOps exception integration: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "contracts/argocd-image-exceptions.json",
    )
    parser.add_argument("--gitops", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.contract.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read exception contract: {exc}", file=sys.stderr)
        return 1
    errors = validate_contract(value)
    images = {
        str(exception.get("image", ""))
        for exception in value.get("exceptions") or []
        if isinstance(exception, dict)
    }
    if args.gitops is not None:
        errors.extend(gitops_contract_errors(images, args.gitops.resolve()))
    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    suffix = " with GitOps equality" if args.gitops is not None else ""
    print(f"Argo exact-digest exception contract passed{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
