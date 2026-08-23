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

try:
    from account_handoff import bootstrap_source_commit, build_account_handoff
except ModuleNotFoundError:
    from scripts.account_handoff import bootstrap_source_commit, build_account_handoff


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
            f"{github_org}/.github/.github/workflows/{workflow}@refs/tags/v5.0.0"
        )
        if identity["job_workflow_ref"] != expected_job:
            raise ValueError(
                f"artifact release identity {capability} has wrong reusable workflow"
            )
        validated[capability] = {field: identity[field] for field in sorted(required)}
    return validated


def validated_dr_evidence_identity(
    value: Any, github_pool: str, github_org: str
) -> dict[str, Any]:
    required_fields = {
        "workload_identity_provider",
        "job_workflow_ref",
        "principals",
    }
    if not isinstance(value, dict) or set(value) != required_fields:
        raise ValueError("platform_contract DR evidence identity is not exact")
    if value["workload_identity_provider"] != f"{github_pool}/providers/gh-dr-evidence":
        raise ValueError("platform_contract DR evidence provider is wrong")
    expected_job = (
        f"{github_org}/.github/.github/workflows/"
        "reusable-dr-evidence.yml@refs/tags/v5.0.0"
    )
    if value["job_workflow_ref"] != expected_job:
        raise ValueError("platform_contract DR evidence reusable workflow is wrong")
    expected_principals = {
        f"{repository}:{environment}"
        for repository in (
            "bootstrap",
            "github-config",
            "infrastructure-live",
            "gitops",
        )
        for environment in ("scratch", "staging")
    }
    principals = value["principals"]
    if not isinstance(principals, dict) or set(principals) != expected_principals:
        raise ValueError("platform_contract DR evidence principal inventory is not exact")
    for key, principal in principals.items():
        repository, environment = key.split(":", maxsplit=1)
        expected_pattern = (
            rf"principal://iam\.googleapis\.com/{re.escape(github_pool)}/subject/"
            rf"dr-evidence:repo:{re.escape(github_org)}@[0-9]+/"
            rf"{re.escape(repository)}@[0-9]+:environment:{re.escape(environment)}"
        )
        if not isinstance(principal, str) or re.fullmatch(
            expected_pattern, principal
        ) is None:
            raise ValueError(f"platform_contract DR evidence principal is wrong: {key}")
    return {
        "job_workflow_ref": value["job_workflow_ref"],
        "principals": {key: principals[key] for key in sorted(principals)},
        "workload_identity_provider": value["workload_identity_provider"],
    }


def validated_production_qualification_identity(
    value: Any, github_pool: str, github_org: str
) -> dict[str, str]:
    required = {
        "workload_identity_provider",
        "principal",
        "subject",
        "workflow_ref",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("platform_contract production qualification identity is not exact")
    subject = value["subject"]
    if not isinstance(subject, str) or re.fullmatch(
        rf"repo:{re.escape(github_org)}@[0-9]+/gitops@[0-9]+:environment:production",
        subject,
    ) is None:
        raise ValueError("platform_contract production qualification subject is wrong")
    expected = {
        "workload_identity_provider": (
            f"{github_pool}/providers/gh-production-qualification"
        ),
        "principal": (
            f"principal://iam.googleapis.com/{github_pool}/subject/"
            f"production-qualification:{subject}"
        ),
        "subject": subject,
        "workflow_ref": (
            f"{github_org}/gitops/.github/workflows/"
            "production-qualification-evidence.yml@refs/heads/main"
        ),
    }
    if value != expected:
        raise ValueError("platform_contract production qualification identity differs")
    return expected


def validated_bazel_cache_identity(
    value: Any, github_pool: str, github_org: str
) -> dict[str, Any]:
    required = {
        "workload_identity_provider",
        "repository",
        "repository_owner_id",
        "repository_id",
        "routes",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("platform_contract Bazel cache identity is not exact")
    repository = f"{github_org}/mindclade-internal-monorepo"
    if value["workload_identity_provider"] != (
        f"{github_pool}/providers/gh-bazel-cache"
    ):
        raise ValueError("platform_contract Bazel cache provider is wrong")
    if value["repository"] != repository:
        raise ValueError("platform_contract Bazel cache repository is wrong")
    for field in ("repository_owner_id", "repository_id"):
        if not isinstance(value[field], str) or re.fullmatch(
            r"[0-9]+", value[field]
        ) is None:
            raise ValueError(f"platform_contract Bazel cache {field} is wrong")
    route_specs = {
        "pull-request-read": (
            "read",
            "pull_request",
            "pull-request-merge",
            f"{repository}/.github/workflows/presubmit.yml",
        ),
        "trusted-main-write": (
            "write",
            "push",
            "protected-main",
            f"{repository}/.github/workflows/presubmit.yml",
        ),
        "merge-group-write": (
            "write",
            "merge_group",
            "protected-merge-queue",
            f"{repository}/.github/workflows/presubmit.yml",
        ),
        "nightly-write": (
            "write",
            "schedule",
            "protected-main",
            f"{repository}/.github/workflows/nightly.yml",
        ),
    }
    routes = value["routes"]
    if not isinstance(routes, dict) or set(routes) != set(route_specs):
        raise ValueError("platform_contract Bazel cache route inventory is not exact")
    validated_routes: dict[str, dict[str, str]] = {}
    for route, (access, event_name, ref_policy, workflow_path) in route_specs.items():
        expected = {
            "access": access,
            "event_name": event_name,
            "principal": (
                f"principal://iam.googleapis.com/{github_pool}/subject/"
                f"bazel-cache:{route}"
            ),
            "ref_policy": ref_policy,
            "workflow_path": workflow_path,
        }
        if routes[route] != expected:
            raise ValueError(f"platform_contract Bazel cache route is wrong: {route}")
        validated_routes[route] = expected
    return {
        "repository": repository,
        "repository_id": value["repository_id"],
        "repository_owner_id": value["repository_owner_id"],
        "routes": validated_routes,
        "workload_identity_provider": value["workload_identity_provider"],
    }


def validated_workstation_image_identity(
    value: Any, github_pool: str, github_org: str
) -> dict[str, str]:
    required = {
        "workload_identity_provider",
        "principal",
        "repository",
        "repository_id",
        "subject",
        "workflow_ref",
        "job_workflow_ref",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("platform_contract workstation image identity is not exact")
    repository = f"{github_org}/mindclade-internal-monorepo"
    subject = value["subject"]
    if not isinstance(subject, str) or re.fullmatch(
        rf"repo:{re.escape(github_org)}@[0-9]+/mindclade-internal-monorepo@[0-9]+:"
        r"environment:workstation-image-publication",
        subject,
    ) is None:
        raise ValueError("platform_contract workstation image subject is wrong")
    expected = {
        "workload_identity_provider": f"{github_pool}/providers/gh-workstation-image",
        "principal": f"principal://iam.googleapis.com/{github_pool}/subject/workstation-image:{subject}",
        "repository": repository,
        "repository_id": value["repository_id"],
        "subject": subject,
        "workflow_ref": f"{repository}/.github/workflows/nixos-image.yml@refs/heads/main",
        "job_workflow_ref": (
            f"{github_org}/.github/.github/workflows/"
            "reusable-nixos-gce-image-publish.yml@refs/tags/v5.0.0"
        ),
    }
    if not isinstance(value["repository_id"], str) or re.fullmatch(
        r"[0-9]+", value["repository_id"]
    ) is None:
        raise ValueError("platform_contract workstation image repository ID is wrong")
    if value != expected:
        raise ValueError("platform_contract workstation image identity differs")
    return expected


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
        source_commit = bootstrap_source_commit(bootstrap)
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
        if contract.get("contract_version") != "1.6.0":
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
        dr_evidence_identity = validated_dr_evidence_identity(
            need(github, "dr_evidence_identity", "github"), pool, github_org
        )
        production_qualification_identity = validated_production_qualification_identity(
            need(github, "production_qualification_identity", "github"),
            pool,
            github_org,
        )
        bazel_cache_identity = validated_bazel_cache_identity(
            need(github, "bazel_cache_identity", "github"), pool, github_org
        )
        workstation_image_identity = validated_workstation_image_identity(
            need(github, "workstation_image_identity", "github"), pool, github_org
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
            "DR_EVIDENCE_IDENTITY_JSON": json.dumps(
                dr_evidence_identity, sort_keys=True, separators=(",", ":")
            ),
            "BAZEL_CACHE_IDENTITY_JSON": json.dumps(
                bazel_cache_identity, sort_keys=True, separators=(",", ":")
            ),
            "WORKSTATION_IMAGE_IDENTITY_JSON": json.dumps(
                workstation_image_identity, sort_keys=True, separators=(",", ":")
            ),
            "PRODUCTION_QUALIFICATION_IDENTITY_JSON": json.dumps(
                production_qualification_identity,
                sort_keys=True,
                separators=(",", ":"),
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
        values["BOOTSTRAP_ACCOUNT_HANDOFF_JSON"] = json.dumps(
            build_account_handoff(contract, values, source_commit),
            sort_keys=True,
            separators=(",", ":"),
        )
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
