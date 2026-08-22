#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Export exact applied GitOps and supply-chain identities for github-config."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
UNITS = {
    "automation_iam": ROOT / "1-org/automation-iam",
    "gitops_identities": ROOT / "5-workloads/shared/control-plane-identities",
    "binary_authorization": ROOT / "5-workloads/production/binary-authorization",
    "qualification_evidence": ROOT
    / "5-workloads/shared/production-qualification-evidence",
}
ATTESTORS = ("build-attestor", "qualification-attestor", "deployment-attestor")
CAPABILITY_SERVICE_ACCOUNTS = {
    "canary": ("SA_ARC_CANARY", "sa-arc-canary"),
    "builder": ("SA_ARTIFACT_BUILDER", "sa-artifact-builder"),
    "qualification-reader": (
        "SA_ARTIFACT_QUALIFICATION_READER",
        "sa-artifact-qual-reader",
    ),
    "qualifier": ("SA_ARTIFACT_QUALIFIER", "sa-artifact-qualifier"),
    "signer": ("SA_ARTIFACT_SIGNER", "sa-artifact-signer"),
    "promoter": ("SA_ARTIFACT_PROMOTER", "sa-artifact-promoter"),
}
SERVICE_ACCOUNT = re.compile(
    r"^[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com$"
)
PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
KEY_VERSION = re.compile(
    r"^projects/[a-z][a-z0-9-]{4,28}[a-z0-9]/locations/[a-z0-9-]+/"
    r"keyRings/[A-Za-z0-9_-]+/cryptoKeys/attestor-deployment-attestor/"
    r"cryptoKeyVersions/[1-9][0-9]*$"
)
ELIGIBILITY_KEY_VERSION = re.compile(
    r"^projects/[a-z][a-z0-9-]{4,28}[a-z0-9]/locations/[a-z0-9-]+/"
    r"keyRings/[A-Za-z0-9_-]+/cryptoKeys/production-eligibility-decisions/"
    r"cryptoKeyVersions/[1-9][0-9]*$"
)
MOCK_VALUE = re.compile(
    r"(?i)(?:^|[-_/.])(mock|unknown|placeholder|example|changeme)(?:$|[-_/.])|"
    r"\(known after apply\)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument(
        "--terragrunt", default=os.environ.get("TERRAGRUNT", "terragrunt")
    )
    return parser.parse_args()


def require_clean_source(expected_commit: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", expected_commit) is None:
        raise ValueError("expected source commit must be an immutable full SHA")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    if status.strip():
        raise ValueError("infrastructure-live source tree must be clean before export")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("source commit is not an immutable full SHA")
    if commit != expected_commit:
        raise ValueError("source commit differs from --expected-source-commit")
    return commit


def output_value(payload: dict[str, Any], name: str, unit: str) -> Any:
    item = payload.get(name)
    if not isinstance(item, dict) or "value" not in item:
        raise ValueError(f"{unit} output is missing {name}")
    if item.get("sensitive") is not False:
        raise ValueError(f"{unit}.{name} must be an explicitly non-sensitive output")
    value = item["value"]
    if value is None:
        raise ValueError(f"{unit}.{name} is null; apply the authoritative unit first")
    return value


def read_outputs(terragrunt: str, unit: str, directory: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["TG_STRICT_MODE"] = "true"
    result = subprocess.run(
        [terragrunt, "output", "-json", "--non-interactive"],
        cwd=directory,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{unit} did not return a Terraform output JSON object"
        ) from error
    if not isinstance(payload, dict):
        raise ValueError(f"{unit} output payload must be an object")
    return payload


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if MOCK_VALUE.search(value):
        raise ValueError(f"{label} contains a mock, unknown, or planned value")
    return value


def require_service_account(
    value: Any, label: str, *, expected_account: str, project_suffix: str
) -> str:
    account = require_string(value, label)
    match = SERVICE_ACCOUNT.fullmatch(account)
    if match is None:
        raise ValueError(f"{label} is not an exact service-account email")
    local_part, _, project_domain = account.partition("@")
    project = project_domain.removesuffix(".iam.gserviceaccount.com")
    if local_part != expected_account:
        raise ValueError(f"{label} names the wrong service account")
    if not project.endswith(project_suffix):
        raise ValueError(f"{label} belongs to the wrong project trust domain")
    return account


def bazel_cache_handoff(
    automation_outputs: dict[str, Any], ci_project_id: str
) -> dict[str, str]:
    applied = require_mapping(
        output_value(
            automation_outputs,
            "bazel_cache_identity_contract",
            "automation_iam",
        ),
        "bazel_cache_identity_contract",
    )
    applied_fields = {
        "WIF_PROVIDER_BAZEL_CACHE",
        "SA_BAZEL_CACHE_READER",
        "SA_BAZEL_CACHE_WRITER",
        "repository",
        "repository_owner_id",
        "repository_id",
        "routes",
    }
    if set(applied) != applied_fields:
        raise ValueError("applied Bazel cache identity field inventory is not exact")
    try:
        bootstrap = json.loads(
            require_string(
                os.environ.get("BAZEL_CACHE_IDENTITY_JSON"),
                "environment BAZEL_CACHE_IDENTITY_JSON",
            )
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            "environment BAZEL_CACHE_IDENTITY_JSON is not valid JSON"
        ) from error
    bootstrap_fields = {
        "workload_identity_provider",
        "repository",
        "repository_owner_id",
        "repository_id",
        "routes",
    }
    if not isinstance(bootstrap, dict) or set(bootstrap) != bootstrap_fields:
        raise ValueError("bootstrap Bazel cache identity field inventory is not exact")
    applied_source = {
        "workload_identity_provider": applied["WIF_PROVIDER_BAZEL_CACHE"],
        "repository": applied["repository"],
        "repository_owner_id": applied["repository_owner_id"],
        "repository_id": applied["repository_id"],
        "routes": applied["routes"],
    }
    if applied_source != bootstrap:
        raise ValueError("applied Bazel cache identity differs from bootstrap")

    provider = require_string(
        applied["WIF_PROVIDER_BAZEL_CACHE"], "WIF_PROVIDER_BAZEL_CACHE"
    )
    provider_match = re.fullmatch(
        r"(projects/[0-9]+/locations/global/workloadIdentityPools/github)"
        r"/providers/gh-bazel-cache",
        provider,
    )
    if provider_match is None:
        raise ValueError("WIF_PROVIDER_BAZEL_CACHE is not the dedicated provider")
    repository = "mindclade/mindclade-internal-monorepo"
    if applied["repository"] != repository:
        raise ValueError("applied Bazel cache repository is not exact")
    for field in ("repository_owner_id", "repository_id"):
        if re.fullmatch(r"[0-9]+", str(applied[field])) is None:
            raise ValueError(f"applied Bazel cache {field} is not immutable")

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
    routes = applied["routes"]
    if not isinstance(routes, dict) or set(routes) != set(route_specs):
        raise ValueError("applied Bazel cache route inventory is not exact")
    for route, (access, event_name, ref_policy, workflow_path) in route_specs.items():
        expected = {
            "access": access,
            "event_name": event_name,
            "principal": (
                "principal://iam.googleapis.com/"
                f"{provider_match.group(1)}/subject/bazel-cache:{route}"
            ),
            "ref_policy": ref_policy,
            "workflow_path": workflow_path,
        }
        if routes[route] != expected:
            raise ValueError(f"applied Bazel cache route is not exact: {route}")

    reader = require_service_account(
        applied["SA_BAZEL_CACHE_READER"],
        "SA_BAZEL_CACHE_READER",
        expected_account="bazel-cache-reader",
        project_suffix="-common-ci",
    )
    writer = require_service_account(
        applied["SA_BAZEL_CACHE_WRITER"],
        "SA_BAZEL_CACHE_WRITER",
        expected_account="bazel-cache-writer",
        project_suffix="-common-ci",
    )
    if not all(
        account.endswith(f"@{ci_project_id}.iam.gserviceaccount.com")
        for account in (reader, writer)
    ):
        raise ValueError("Bazel cache service accounts disagree with ci_project_id")
    return {
        "WIF_PROVIDER_BAZEL_CACHE": provider,
        "SA_BAZEL_CACHE_READER": reader,
        "SA_BAZEL_CACHE_WRITER": writer,
    }


def compile_contract(
    automation_outputs: dict[str, Any],
    gitops_outputs: dict[str, Any],
    binauthz_outputs: dict[str, Any],
    qualification_outputs: dict[str, Any],
    source_commit: str,
) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("source commit must be an immutable full SHA")
    release_identities = require_mapping(
        output_value(
            automation_outputs,
            "artifact_release_identity_contract",
            "automation_iam",
        ),
        "artifact_release_identity_contract",
    )
    try:
        bootstrap_identities = json.loads(
            require_string(
                os.environ.get("ARTIFACT_RELEASE_IDENTITIES_JSON"),
                "environment ARTIFACT_RELEASE_IDENTITIES_JSON",
            )
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            "environment ARTIFACT_RELEASE_IDENTITIES_JSON is not valid JSON"
        ) from error
    if not isinstance(bootstrap_identities, dict) or (
        set(bootstrap_identities) != set(CAPABILITY_SERVICE_ACCOUNTS)
        or set(release_identities) != set(CAPABILITY_SERVICE_ACCOUNTS)
    ):
        raise ValueError("ARC release identity capability inventory is not exact")
    release_service_accounts: dict[str, str] = {}
    for capability, (variable_name, account_id) in CAPABILITY_SERVICE_ACCOUNTS.items():
        applied = require_mapping(
            release_identities[capability],
            f"artifact_release_identity_contract.{capability}",
        )
        bootstrap_identity = require_mapping(
            bootstrap_identities[capability],
            f"bootstrap artifact release identity {capability}",
        )
        for field in (
            "workload_identity_provider",
            "principal",
            "subject",
            "workflow_ref",
            "job_workflow_ref",
        ):
            if require_string(applied.get(field), f"{capability}.{field}") != (
                require_string(bootstrap_identity.get(field), f"bootstrap {capability}.{field}")
            ):
                raise ValueError(
                    f"applied {capability}.{field} differs from the bootstrap contract"
                )
        release_service_accounts[variable_name] = require_service_account(
            applied.get("service_account"),
            variable_name,
            expected_account=account_id,
            project_suffix="-common-ci",
        )

    ci_project_id = require_string(
        output_value(automation_outputs, "ci_project_id", "automation_iam"),
        "automation_iam.ci_project_id",
    )
    if PROJECT_ID.fullmatch(ci_project_id) is None or not ci_project_id.endswith(
        "-common-ci"
    ):
        raise ValueError("automation_iam.ci_project_id belongs to the wrong trust domain")
    if any(
        not account.endswith(f"@{ci_project_id}.iam.gserviceaccount.com")
        for account in release_service_accounts.values()
    ):
        raise ValueError("ARC service accounts disagree with automation_iam.ci_project_id")
    cache_variables = bazel_cache_handoff(automation_outputs, ci_project_id)

    identities = require_mapping(
        output_value(
            gitops_outputs, "github_config_identity_handoff", "gitops_identities"
        ),
        "github_config_identity_handoff",
    )
    qualification_handoff = require_mapping(
        output_value(
            gitops_outputs,
            "production_qualification_identity_handoff",
            "gitops_identities",
        ),
        "production_qualification_identity_handoff",
    )
    qualification_identity = require_mapping(
        output_value(
            gitops_outputs,
            "production_qualification_identity_contract",
            "gitops_identities",
        ),
        "production_qualification_identity_contract",
    )
    try:
        bootstrap_qualification_identity = json.loads(
            require_string(
                os.environ.get("PRODUCTION_QUALIFICATION_IDENTITY_JSON"),
                "environment PRODUCTION_QUALIFICATION_IDENTITY_JSON",
            )
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            "environment PRODUCTION_QUALIFICATION_IDENTITY_JSON is not valid JSON"
        ) from error
    qualification_fields = {
        "workload_identity_provider",
        "principal",
        "subject",
        "workflow_ref",
    }
    if (
        not isinstance(bootstrap_qualification_identity, dict)
        or set(bootstrap_qualification_identity) != qualification_fields
        or set(qualification_identity) != qualification_fields
        or qualification_identity != bootstrap_qualification_identity
    ):
        raise ValueError(
            "applied production qualification identity differs from bootstrap"
        )
    if qualification_identity["workflow_ref"] != (
        "mindclade/gitops/.github/workflows/"
        "production-qualification-evidence.yml@refs/heads/main"
    ):
        raise ValueError("production qualification workflow_ref is not exact")
    qualification_provider = require_string(
        qualification_identity["workload_identity_provider"],
        "production qualification workload identity provider",
    )
    if not qualification_provider.endswith(
        "/workloadIdentityPools/github/providers/gh-production-qualification"
    ):
        raise ValueError("production qualification WIF provider is not exact")
    if qualification_handoff.get(
        "WIF_PROVIDER_PRODUCTION_QUALIFICATION"
    ) != qualification_provider:
        raise ValueError("production qualification handoff provider differs")
    project_id = require_string(
        output_value(binauthz_outputs, "project_id", "binary_authorization"),
        "binary_authorization.project_id",
    )
    if PROJECT_ID.fullmatch(project_id) is None:
        raise ValueError("binary_authorization.project_id is not a valid project ID")
    if not project_id.endswith("-production-platform"):
        raise ValueError(
            "binary_authorization.project_id belongs to the wrong environment"
        )
    attestor_names = require_mapping(
        output_value(binauthz_outputs, "attestor_names", "binary_authorization"),
        "binary_authorization.attestor_names",
    )
    key_versions = require_mapping(
        output_value(binauthz_outputs, "attestor_key_versions", "binary_authorization"),
        "binary_authorization.attestor_key_versions",
    )
    enforcement = require_string(
        output_value(binauthz_outputs, "enforcement_mode", "binary_authorization"),
        "binary_authorization.enforcement_mode",
    )
    if enforcement != "ENFORCED_BLOCK_AND_AUDIT_LOG":
        raise ValueError("production Binary Authorization is not blocking")

    exact_attestors: dict[str, str] = {}
    for name in ATTESTORS:
        value = require_string(attestor_names.get(name), f"attestor_names.{name}")
        if value != name:
            raise ValueError(f"attestor_names.{name} must equal its applied short name")
        exact_attestors[name] = value
    deployment_key = require_string(
        key_versions.get("deployment-attestor"),
        "attestor_key_versions.deployment-attestor",
    )
    if KEY_VERSION.fullmatch(deployment_key) is None:
        raise ValueError("deployment attestor key is not an immutable KMS key version")

    qualification_bucket = require_mapping(
        output_value(
            qualification_outputs, "bucket", "qualification_evidence"
        ),
        "qualification_evidence.bucket",
    )
    bucket_name = require_string(
        qualification_bucket.get("name"), "qualification evidence bucket name"
    )
    if bucket_name != "mc-production-qualification-evidence":
        raise ValueError("production qualification evidence bucket name is not exact")
    qualification_project = require_string(
        qualification_handoff.get("PRODUCTION_QUALIFICATION_PROJECT"),
        "PRODUCTION_QUALIFICATION_PROJECT",
    )
    if qualification_project != "mc-common-security":
        raise ValueError("production qualification project is not exact")
    qualification_secret = require_string(
        qualification_handoff.get("PRODUCTION_QUALIFICATION_PRIVATE_KEY_SECRET"),
        "PRODUCTION_QUALIFICATION_PRIVATE_KEY_SECRET",
    )
    if qualification_secret != "github-app-production-qualification-reader-pem":
        raise ValueError("production qualification private-key secret ID is not exact")
    eligibility_key_version = require_string(
        qualification_handoff.get("PRODUCTION_ELIGIBILITY_KMS_KEY_VERSION"),
        "PRODUCTION_ELIGIBILITY_KMS_KEY_VERSION",
    )
    if ELIGIBILITY_KEY_VERSION.fullmatch(eligibility_key_version) is None:
        raise ValueError("production eligibility signer is not an immutable KMS key version")
    eligibility_key_id = require_string(
        qualification_handoff.get("PRODUCTION_ELIGIBILITY_SIGNING_KEY_ID"),
        "PRODUCTION_ELIGIBILITY_SIGNING_KEY_ID",
    )
    if eligibility_key_id != "production-eligibility-v1":
        raise ValueError("production eligibility signing key ID is not exact")

    variables = {
        "CI_PROJECT_ID": ci_project_id,
        **release_service_accounts,
        **cache_variables,
        "SA_GITOPS_RENDER": require_service_account(
            identities.get("SA_GITOPS_RENDER"),
            "SA_GITOPS_RENDER",
            expected_account="sa-gitops-render",
            project_suffix="-common-security",
        ),
        "SA_GITOPS_VERIFIER": require_service_account(
            identities.get("SA_GITOPS_VERIFIER"),
            "SA_GITOPS_VERIFIER",
            expected_account="sa-gitops-verifier",
            project_suffix="-common-security",
        ),
        "WIF_PROVIDER_PRODUCTION_QUALIFICATION": qualification_provider,
        "SA_PRODUCTION_QUALIFICATION_EVALUATOR": require_service_account(
            qualification_handoff.get("SA_PRODUCTION_QUALIFICATION_EVALUATOR"),
            "SA_PRODUCTION_QUALIFICATION_EVALUATOR",
            expected_account="sa-prod-qual-evaluator",
            project_suffix="-common-security",
        ),
        "SA_PRODUCTION_QUALIFICATION_READER": require_service_account(
            qualification_handoff.get("SA_PRODUCTION_QUALIFICATION_READER"),
            "SA_PRODUCTION_QUALIFICATION_READER",
            expected_account="sa-prod-qual-reader",
            project_suffix="-common-security",
        ),
        "SA_PRODUCTION_QUALIFICATION_WRITER": require_service_account(
            qualification_handoff.get("SA_PRODUCTION_QUALIFICATION_WRITER"),
            "SA_PRODUCTION_QUALIFICATION_WRITER",
            expected_account="sa-prod-qual-writer",
            project_suffix="-common-security",
        ),
        "PRODUCTION_QUALIFICATION_PROJECT": qualification_project,
        "PRODUCTION_QUALIFICATION_BUCKET": bucket_name,
        "PRODUCTION_QUALIFICATION_PRIVATE_KEY_SECRET": qualification_secret,
        "PRODUCTION_ELIGIBILITY_SIGNING_KEY_ID": eligibility_key_id,
        "PRODUCTION_ELIGIBILITY_KMS_KEY_VERSION": eligibility_key_version,
        "BINAUTHZ_BUILD_ATTESTOR_PROJECT": project_id,
        "BINAUTHZ_BUILD_ATTESTOR": exact_attestors["build-attestor"],
        "BINAUTHZ_QUALIFICATION_ATTESTOR_PROJECT": project_id,
        "BINAUTHZ_QUALIFICATION_ATTESTOR": exact_attestors["qualification-attestor"],
        "BINAUTHZ_DEPLOYMENT_ATTESTOR_PROJECT": project_id,
        "BINAUTHZ_DEPLOYMENT_ATTESTOR": exact_attestors["deployment-attestor"],
        "BINAUTHZ_DEPLOYMENT_ATTESTOR_KEY_VERSION": deployment_key,
    }
    return {
        "contract_version": "1.4.0",
        "producer": "mindclade/infrastructure-live",
        "source_commit": source_commit,
        "environment": "production",
        "source_units": {
            name: str(path.relative_to(ROOT)) for name, path in UNITS.items()
        },
        "variables": variables,
        "credential_material_included": False,
    }


def write_contract(target: Path, contract: dict[str, Any]) -> None:
    target = target.resolve()
    if target == ROOT or ROOT in target.parents:
        raise ValueError(
            "applied handoff evidence must be written outside the repository"
        )
    if target.exists():
        raise ValueError("refusing to overwrite existing applied handoff evidence")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(contract, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    try:
        commit = require_clean_source(args.expected_source_commit)
        payloads = {
            name: read_outputs(args.terragrunt, name, directory)
            for name, directory in UNITS.items()
        }
        contract = compile_contract(
            payloads["automation_iam"],
            payloads["gitops_identities"],
            payloads["binary_authorization"],
            payloads["qualification_evidence"],
            commit,
        )
        write_contract(args.output, contract)
        print(f"wrote applied control-plane handoff: {args.output.resolve()}")
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
