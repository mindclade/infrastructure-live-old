#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

#
"""Validate the stable account.hcl contract and its runtime values."""

from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "account.hcl"
REQUIRED = {
    "GCP_ORG_ID": r"^[0-9]+$",
    "BILLING_ACCOUNT": r"^[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}-[0-9A-Fa-f]{6}$",
    "CLOUD_IDENTITY_CUSTOMER_ID": r"^C[0-9A-Za-z]+$",
    "BOOTSTRAP_SEED_PROJECT_ID": r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$",
    "BOOTSTRAP_CICD_PROJECT_ID": r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$",
    "BOOTSTRAP_CICD_PROJECT_NUMBER": r"^[0-9]+$",
    "GITHUB_WIF_POOL_NAME": r"^projects/[0-9]+/locations/global/workloadIdentityPools/[a-z0-9-]+$",
    "ARTIFACT_RELEASE_IDENTITIES_JSON": r"^\{.+\}$",
    "DR_EVIDENCE_IDENTITY_JSON": r"^\{.+\}$",
    "TFSTATE_BUCKET_DEVELOPMENT": r"^[a-z0-9][a-z0-9._-]{1,221}[a-z0-9]$",
    "TFSTATE_BUCKET_STAGING": r"^[a-z0-9][a-z0-9._-]{1,221}[a-z0-9]$",
    "TFSTATE_BUCKET_PRODUCTION": r"^[a-z0-9][a-z0-9._-]{1,221}[a-z0-9]$",
    "SA_TF_LIVE_PLAN": r"^[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com$",
    "SA_TF_LIVE_APPLY_FOUNDATION": r"^[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com$",
    "SA_TF_LIVE_APPLY_DEVELOPMENT": r"^[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com$",
    "SA_TF_LIVE_APPLY_STAGING": r"^[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com$",
    "SA_TF_LIVE_APPLY_PRODUCTION": r"^[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com$",
}
OPTIONAL = {
    "RESOURCE_PREFIX": "mc",
    "PRIMARY_REGION": "us-central1",
    "STATE_LOCATION": "US",
    "GPU_ZONE": "us-central1-b",
    "DOMAIN": "mindclade.com",
    "MONOREPO_ORG": "mindclade",
    "ORG_POLICY_ACTIVATION_PHASE": "baseline",
}


def release_identity_errors(payload: str, pool: str, organization: str) -> list[str]:
    try:
        identities = json.loads(payload)
    except json.JSONDecodeError:
        return ["ARTIFACT_RELEASE_IDENTITIES_JSON is not valid JSON"]
    expected = {
        "canary",
        "builder",
        "qualification-reader",
        "qualifier",
        "signer",
        "promoter",
    }
    if not isinstance(identities, dict) or set(identities) != expected:
        return ["ARTIFACT_RELEASE_IDENTITIES_JSON capability inventory is not exact"]
    errors: list[str] = []
    for capability, identity in identities.items():
        if not isinstance(identity, dict):
            errors.append(f"artifact release identity is not an object: {capability}")
            continue
        provider_id = (
            "gh-mindclade-internal-monorepo"
            if capability == "signer"
            else f"gh-arc-{capability}"
        )
        if identity.get("workload_identity_provider") != f"{pool}/providers/{provider_id}":
            errors.append(f"artifact release provider differs: {capability}")
        subject = identity.get("subject")
        if not isinstance(subject, str) or re.fullmatch(
            rf"repo:{re.escape(organization)}@[0-9]+/mindclade-internal-monorepo@[0-9]+:"
            rf"{'environment:release' if capability in {'signer', 'promoter'} else 'ref:refs/heads/main'}",
            subject,
        ) is None:
            errors.append(f"artifact release subject differs: {capability}")
            continue
        mapped_subject = subject if capability == "signer" else f"arc-{capability}:{subject}"
        if identity.get("principal") != (
            f"principal://iam.googleapis.com/{pool}/subject/{mapped_subject}"
        ):
            errors.append(f"artifact release principal differs: {capability}")
        if identity.get("workflow_ref") != (
            f"{organization}/mindclade-internal-monorepo/.github/workflows/"
            "release.yml@refs/heads/main"
        ):
            errors.append(f"artifact release caller differs: {capability}")
        job = identity.get("job_workflow_ref")
        if not isinstance(job, str) or not job.startswith(
            f"{organization}/.github/.github/workflows/reusable-"
        ) or not job.endswith("@refs/tags/v4.0.0"):
            errors.append(f"artifact release workflow differs: {capability}")
    return errors


def dr_evidence_identity_errors(
    payload: str, pool: str, organization: str
) -> list[str]:
    try:
        identity = json.loads(payload)
    except json.JSONDecodeError:
        return ["DR_EVIDENCE_IDENTITY_JSON is not valid JSON"]
    required_fields = {
        "workload_identity_provider",
        "job_workflow_ref",
        "principals",
    }
    if not isinstance(identity, dict) or set(identity) != required_fields:
        return ["DR evidence identity contract is not exact"]
    if identity["workload_identity_provider"] != f"{pool}/providers/gh-dr-evidence":
        return ["DR evidence identity provider differs"]
    if identity["job_workflow_ref"] != (
        f"{organization}/.github/.github/workflows/"
        "reusable-dr-evidence.yml@refs/tags/v4.0.0"
    ):
        return ["DR evidence reusable workflow differs"]
    expected = {
        f"{repository}:{environment}"
        for repository in (
            "bootstrap",
            "github-config",
            "infrastructure-live",
            "gitops",
        )
        for environment in ("scratch", "staging")
    }
    principals = identity["principals"]
    if not isinstance(principals, dict) or set(principals) != expected:
        return ["DR evidence principal inventory is not exact"]
    errors: list[str] = []
    for key, principal in principals.items():
        repository, environment = key.split(":", maxsplit=1)
        expected_pattern = (
            rf"principal://iam\.googleapis\.com/{re.escape(pool)}/subject/"
            rf"dr-evidence:repo:{re.escape(organization)}@[0-9]+/"
            rf"{re.escape(repository)}@[0-9]+:environment:{re.escape(environment)}"
        )
        if not isinstance(principal, str) or re.fullmatch(
            expected_pattern, principal
        ) is None:
            errors.append(f"DR evidence principal differs: {key}")
    return errors


def source_errors() -> list[str]:
    text = SOURCE.read_text(encoding="utf-8")
    errors = []
    if "REPLACE" in text or "000000000000" in text or "XXXXXX-XXXXXX-XXXXXX" in text:
        errors.append("account.hcl contains committed placeholder identifiers")
    for name in (*REQUIRED, *OPTIONAL):
        if f'get_env("{name}"' not in text:
            errors.append(f"account.hcl does not consume {name}")
    if re.search(
        r'(?m)^\s*(?:org_id|billing_account|seed_project_id|cicd_project_id)\s*=\s*"',
        text,
    ):
        errors.append("account.hcl hard-codes an organization or project identifier")
    return errors


def runtime_values() -> tuple[dict[str, str], list[str]]:
    values = {name: os.environ.get(name, "") for name in REQUIRED}
    values.update(
        {name: os.environ.get(name, default) for name, default in OPTIONAL.items()}
    )
    errors = []
    for name, pat in REQUIRED.items():
        if not re.fullmatch(pat, values[name]):
            errors.append(f"invalid or missing runtime account field: {name}")
    if not re.fullmatch(r"^[a-z][a-z0-9]{1,3}$", values["RESOURCE_PREFIX"]):
        errors.append("invalid RESOURCE_PREFIX")
    if not re.fullmatch(r"^[a-z]+-[a-z0-9]+[0-9]$", values["PRIMARY_REGION"]):
        errors.append("invalid PRIMARY_REGION")
    if not re.fullmatch(r"^[a-z]+-[a-z0-9]+[0-9]-[a-z]$", values["GPU_ZONE"]):
        errors.append("invalid GPU_ZONE")
    if not values["GPU_ZONE"].startswith(values["PRIMARY_REGION"] + "-"):
        errors.append("GPU_ZONE must belong to PRIMARY_REGION")
    if not re.fullmatch(r"^[A-Za-z0-9.-]+$", values["DOMAIN"]):
        errors.append("invalid DOMAIN")
    if not re.fullmatch(r"^[A-Za-z0-9_.-]+$", values["MONOREPO_ORG"]):
        errors.append("invalid MONOREPO_ORG")
    if values["ORG_POLICY_ACTIVATION_PHASE"] not in {"baseline", "extended"}:
        errors.append("ORG_POLICY_ACTIVATION_PHASE must be baseline or extended")
    errors.extend(
        release_identity_errors(
            values["ARTIFACT_RELEASE_IDENTITIES_JSON"],
            values["GITHUB_WIF_POOL_NAME"],
            values["MONOREPO_ORG"],
        )
    )
    errors.extend(
        dr_evidence_identity_errors(
            values["DR_EVIDENCE_IDENTITY_JSON"],
            values["GITHUB_WIF_POOL_NAME"],
            values["MONOREPO_ORG"],
        )
    )
    return dict(sorted(values.items())), errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    errors = source_errors()
    values = {}
    if args.runtime:
        values, runtime = runtime_values()
        errors.extend(runtime)
    if errors:
        for e in sorted(set(errors)):
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if args.json:
        if not args.runtime:
            print("ERROR: --json requires --runtime", file=sys.stderr)
            return 2
        print(json.dumps(values, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "account contract source and runtime values passed"
            if args.runtime
            else "account contract source passed"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
