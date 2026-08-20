#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Generate the local infrastructure account environment from bootstrap outputs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def validated_customer_id(value: str) -> str:
    if not re.fullmatch(r"C[0-9A-Za-z]+", value):
        raise ValueError(
            "CLOUD_IDENTITY_CUSTOMER_ID must be the existing immutable directory customer ID"
        )
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "bootstrap",
        nargs="?",
        type=Path,
        default=Path(os.environ.get("BOOTSTRAP_DIR", ROOT.parent / "bootstrap")),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.environ.get("TARGET", ROOT / ".account.env")),
    )
    return parser.parse_args()


def need(mapping: dict[str, Any], key: str, label: str) -> Any:
    value = mapping.get(key)
    if value in (None, ""):
        raise ValueError(f"{label} is missing {key}")
    return value


def validated_retired_buildkite(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("platform_contract buildkite must be an object")
    if value != {
        "enabled": False,
        "workload_identity_pool": None,
        "workload_identity_provider": None,
    }:
        raise ValueError(
            "Buildkite is retired and must publish disabled with null pool and provider"
        )


def validated_release_identities(
    value: Any, github_pool: str, github_org: str
) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        raise ValueError("platform_contract artifact release identities must be an object")
    workflows = {
        "canary": "reusable-arc-wif-canary.yml",
        "builder": "reusable-arc-oci-build.yml",
        "qualification-reader": "reusable-arc-oci-qualify.yml",
        "qualifier": "reusable-arc-qualification-attest.yml",
        "signer": "reusable-binauthz-sign.yml",
        "promoter": "reusable-gitops-promote.yml",
    }
    if set(value) != set(workflows):
        raise ValueError("platform_contract artifact release identity inventory is not exact")
    caller = (
        f"{github_org}/mindclade-internal-monorepo/.github/workflows/"
        "release.yml@refs/heads/main"
    )
    required = {
        "workload_identity_provider",
        "principal",
        "subject",
        "workflow_ref",
        "job_workflow_ref",
    }
    validated: dict[str, dict[str, str]] = {}
    for capability, workflow in workflows.items():
        identity = value[capability]
        if not isinstance(identity, dict) or set(identity) != required:
            raise ValueError(f"artifact release identity {capability} is not exact")
        if not all(
            isinstance(identity[field], str) and identity[field] for field in required
        ):
            raise ValueError(f"artifact release identity {capability} contains an empty field")
        provider_id = (
            "gh-mindclade-internal-monorepo"
            if capability == "signer"
            else f"gh-arc-{capability}"
        )
        if identity["workload_identity_provider"] != (
            f"{github_pool}/providers/{provider_id}"
        ):
            raise ValueError(f"artifact release identity {capability} has wrong provider")
        subject_suffix = (
            "environment:release"
            if capability in {"signer", "promoter"}
            else "ref:refs/heads/main"
        )
        if re.fullmatch(
            rf"repo:{re.escape(github_org)}@[0-9]+/"
            rf"mindclade-internal-monorepo@[0-9]+:{re.escape(subject_suffix)}",
            identity["subject"],
        ) is None:
            raise ValueError(f"artifact release identity {capability} has wrong subject")
        federated_subject = (
            identity["subject"]
            if capability == "signer"
            else f"arc-{capability}:{identity['subject']}"
        )
        expected_principal = (
            f"principal://iam.googleapis.com/{github_pool}/subject/{federated_subject}"
        )
        if identity["principal"] != expected_principal:
            raise ValueError(f"artifact release identity {capability} has wrong principal")
        if identity["workflow_ref"] != caller:
            raise ValueError(f"artifact release identity {capability} has wrong caller")
        expected_job = (
            f"{github_org}/.github/.github/workflows/{workflow}@refs/tags/v4.0.0"
        )
        if identity["job_workflow_ref"] != expected_job:
            raise ValueError(
                f"artifact release identity {capability} has wrong reusable workflow"
            )
        validated[capability] = {field: identity[field] for field in sorted(required)}
    return validated


def main() -> int:
    args = parse_args()
    bootstrap = args.bootstrap.resolve()
    if not bootstrap.is_dir():
        print(f"error: bootstrap repo not found: {bootstrap}", file=sys.stderr)
        return 2
    try:
        cloud_identity_customer_id = validated_customer_id(
            os.environ.get("CLOUD_IDENTITY_CUSTOMER_ID", "")
        )
        output = subprocess.run(
            [
                "terraform",
                f"-chdir={bootstrap}",
                "output",
                "-json",
                "platform_contract",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        contract = json.loads(output.stdout)
        if contract.get("contract_version") != "1.3.0":
            raise ValueError(
                f"unsupported bootstrap platform_contract version: {contract.get('contract_version', 'missing')}"
            )
        state = need(
            need(contract, "state", "platform_contract"), "primary_buckets", "state"
        )
        identities = need(contract, "automation_identities", "platform_contract")
        github = need(contract, "github", "platform_contract")
        pool = str(need(github, "workload_identity_pool", "github"))
        match = re.fullmatch(r"projects/([0-9]+)/.*", pool)
        if match is None:
            raise ValueError("invalid GitHub workload identity pool resource name")
        validated_retired_buildkite(need(contract, "buildkite", "platform_contract"))
        github_org = str(need(github, "organization", "github"))
        release_identities = validated_release_identities(
            need(github, "artifact_release_identities", "github"), pool, github_org
        )
        values = {
            "GCP_ORG_ID": need(contract, "organization_id", "platform_contract"),
            "BILLING_ACCOUNT": need(contract, "billing_account", "platform_contract"),
            "CLOUD_IDENTITY_CUSTOMER_ID": cloud_identity_customer_id,
            "ORG_POLICY_ACTIVATION_PHASE": "baseline",
            "BOOTSTRAP_SEED_PROJECT_ID": need(
                contract, "state_project_id", "platform_contract"
            ),
            "BOOTSTRAP_CICD_PROJECT_ID": need(
                contract, "federation_project_id", "platform_contract"
            ),
            "BOOTSTRAP_CICD_PROJECT_NUMBER": match.group(1),
            "GITHUB_WIF_POOL_NAME": pool,
            "ARTIFACT_RELEASE_IDENTITIES_JSON": json.dumps(
                release_identities, sort_keys=True, separators=(",", ":")
            ),
            "WIF_PROVIDER_SIGNER": need(
                need(github, "artifact_signer", "github"),
                "workload_identity_provider",
                "artifact signer",
            ),
            "ARTIFACT_SIGNER_PRINCIPAL": need(
                github["artifact_signer"], "principal", "artifact signer"
            ),
            "ARTIFACT_SIGNER_JOB_WORKFLOW_REF": need(
                github["artifact_signer"], "job_workflow_ref", "artifact signer"
            ),
            "TFSTATE_BUCKET_DEVELOPMENT": need(
                state, "infrastructure-live-development", "state buckets"
            ),
            "TFSTATE_BUCKET_STAGING": need(
                state, "infrastructure-live-staging", "state buckets"
            ),
            "TFSTATE_BUCKET_PRODUCTION": need(
                state, "infrastructure-live-production", "state buckets"
            ),
            "SA_TF_LIVE_PLAN": need(
                identities, "infrastructure-live-plan", "automation identities"
            ),
            "SA_TF_LIVE_APPLY_FOUNDATION": need(
                identities,
                "infrastructure-live-apply-foundation",
                "automation identities",
            ),
            "SA_TF_LIVE_APPLY_DEVELOPMENT": need(
                identities,
                "infrastructure-live-apply-development",
                "automation identities",
            ),
            "SA_TF_LIVE_APPLY_STAGING": need(
                identities, "infrastructure-live-apply-staging", "automation identities"
            ),
            "SA_TF_LIVE_APPLY_PRODUCTION": need(
                identities,
                "infrastructure-live-apply-production",
                "automation identities",
            ),
            "STATE_LOCATION": need(contract["state"], "primary_location", "state"),
            "MONOREPO_ORG": github_org,
        }
        content = "# Generated from verified bootstrap outputs. Contains identifiers only; never commit.\n"
        content += "".join(
            f"export {name}={shlex.quote(str(value))}\n"
            for name, value in values.items()
        )
        target = args.output.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=target.parent
        )
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        print(f"wrote {target}; source it before Terragrunt commands")
        return 0
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
