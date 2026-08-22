#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Validate the fail-closed Nix binary-cache source and lifecycle contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/nix-binary-cache.json"
SCHEMA = ROOT / "contracts/nix-binary-cache.schema.json"

EXPECTED_BLOCKERS = [
    "attic-client-server-compatibility-qualified",
    "attic-endpoint-tls-qualified",
    "attic-image-mirrored-attested",
    "attic-private-read-auth-qualified",
    "attic-scoped-token-policy-qualified",
    "attic-upstream-production-acceptance",
    "cache-cost-and-growth-limits-approved",
    "cold-warm-tamper-loss-tests-passed",
    "credentialed-saved-plans-retained",
    "gcs-hmac-issued-rotated-out-of-band",
    "gcs-s3-multipart-and-duplicate-writes-qualified",
    "github-environment-applied",
    "infrastructure-resources-applied-qualified",
    "nix-module-v0-4-0-published",
    "nixpkgs-release-line-qualified",
    "postgresql-ha-backup-restore-qualified",
    "protected-publication-caller-reviewed",
    "secret-versions-and-sync-qualified",
    "server-signing-and-token-recovery-qualified",
    "workflow-contract-v5-0-0-published",
]

REQUIRED_SOURCE_PATHS = (
    "1-org/automation-iam/main.tf",
    "1-org/automation-iam/outputs.tf",
    "1-org/kms/terragrunt.hcl",
    "5-workloads/ci/nix-binary-cache/.terraform.lock.hcl",
    "5-workloads/ci/nix-binary-cache/README.md",
    "5-workloads/ci/nix-binary-cache/terragrunt.hcl",
    "5-workloads/ci/nix-cache-secrets/.terraform.lock.hcl",
    "5-workloads/ci/nix-cache-secrets/README.md",
    "5-workloads/ci/nix-cache-secrets/terragrunt.hcl",
    "contracts/nix-binary-cache.json",
    "contracts/nix-binary-cache.schema.json",
)

SECRET_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)


def coded(code: str, message: str) -> str:
    return f"[NIXCACHE-{code}] {message}"


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
        errors.append(
            coded(
                "SCHEMA",
                f"{location} violates {error.validator}; record content is redacted",
            )
        )
    return errors


def walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_strings(child)


def policy_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = document.get("status")
    blockers = document.get("blockers")

    if status == "proposed" and blockers != EXPECTED_BLOCKERS:
        errors.append(
            coded(
                "POLICY",
                "proposed lifecycle must retain the exact reviewed blocker set",
            )
        )
    if status == "qualifying" and (
        not blockers or not set(blockers).issubset(EXPECTED_BLOCKERS)
    ):
        errors.append(
            coded(
                "POLICY",
                "qualifying lifecycle must retain only unresolved reviewed blockers",
            )
        )
    if status in {"qualified", "activated"} and blockers:
        errors.append(coded("POLICY", f"{status} lifecycle cannot retain blockers"))

    client = document.get("client", {})
    publication = document.get("publication", {})
    secrets = document.get("secrets", {})
    if client.get("signing_key_in_scope") is not False:
        errors.append(coded("POLICY", "clients may never receive a cache signing key"))
    if publication.get("client_signing_key_in_scope") is not False:
        errors.append(
            coded("POLICY", "publishers may never receive a cache signing key")
        )
    if publication.get("pull_request_write") is not False:
        errors.append(coded("POLICY", "pull requests may never write the cache"))
    if secrets.get("versions_created_by_terraform") is not False:
        errors.append(coded("POLICY", "Terraform may create containers, not secret values"))
    if secrets.get("github_accessor") is not False:
        errors.append(
            coded("POLICY", "GitHub identities may not read Attic server secrets")
        )

    if any(
        pattern.search(value)
        for value in walk_strings(document)
        for pattern in SECRET_VALUE_PATTERNS
    ):
        errors.append(
            coded("SECRET", "contract contains secret-like material; value is redacted")
        )
    return errors


def source_errors(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_SOURCE_PATHS:
        if not root.joinpath(relative).is_file():
            errors.append(coded("SOURCE", f"required source file is missing: {relative}"))

    executable_source = []
    for suffix in ("*.tf", "*.hcl"):
        executable_source.extend(root.rglob(suffix))
    hmac_resource = re.compile(r'resource\s+"google_storage_hmac_key"')
    if any(
        hmac_resource.search(path.read_text(encoding="utf-8", errors="ignore"))
        for path in executable_source
        if not any(part in {".git", ".terraform", ".terragrunt-cache"} for part in path.parts)
    ):
        errors.append(
            coded(
                "SOURCE",
                "GCS HMAC resources are forbidden because their secret enters Terraform state",
            )
        )

    cache_unit = root / "5-workloads/ci/nix-binary-cache/terragrunt.hcl"
    if cache_unit.is_file():
        text = cache_unit.read_text(encoding="utf-8")
        required = (
            'module_version = "v0.4.0"',
            '//nix_binary_cache?ref=${local.module_version}',
            'reader_members           = []',
            'nix_cache_storage_service_account',
            'access_log_object_prefix = "nix-binary-cache/common-ci/"',
        )
        for fragment in required:
            if fragment not in text:
                errors.append(
                    coded("SOURCE", "cache unit does not preserve its reviewed boundary")
                )
                break
        if "roles/storage.objectAdmin" in text:
            errors.append(coded("SOURCE", "cache unit grants forbidden object-admin access"))

    secret_unit = root / "5-workloads/ci/nix-cache-secrets/terragrunt.hcl"
    if secret_unit.is_file():
        text = secret_unit.read_text(encoding="utf-8")
        if re.search(r"(?:secret_data|secret_payload|secret_version)\s*=", text):
            errors.append(
                coded("SECRET", "secret unit contains a secret value input; value is redacted")
            )
        for required in (
            'service_account = "attic-secret-sync"',
            'namespace       = "mindclade-cache"',
            'module_version = "v0.4.0"',
        ):
            if required not in text:
                errors.append(
                    coded("SOURCE", "secret-container unit does not preserve its reviewed boundary")
                )
                break
    return sorted(set(errors))


def integration_errors(document: dict[str, Any], monorepo: Path) -> list[str]:
    errors: list[str] = []
    population_path = monorepo / "ci/nix_cache/population.json"
    population, load_errors = load_json(population_path, "INTEGRATION")
    errors.extend(load_errors)
    if population is not None:
        publication = document.get("publication", {})
        expected = {
            "attic_client_commit": publication.get("attic_client_commit"),
            "caller_workflow_ref": publication.get("caller_workflow"),
            "dev_shells": publication.get("shells"),
            "package_selector": publication.get("package_selector"),
            "trusted_events": publication.get("trusted_events"),
        }
        for field, value in expected.items():
            if population.get(field) != value:
                errors.append(
                    coded("INTEGRATION", f"population contract mismatch at {field}")
                )
        expected_enabled = document.get("status") in {
            "qualifying",
            "qualified",
            "activated",
        }
        if population.get("activation", {}).get("enabled") is not expected_enabled:
            errors.append(
                coded("INTEGRATION", "population activation does not match lifecycle")
            )

    module_outputs = monorepo / "infra/terraform/modules/nix_binary_cache/outputs.tf"
    if not module_outputs.is_file():
        errors.append(coded("INTEGRATION", "Nix cache module outputs are missing"))
    else:
        text = module_outputs.read_text(encoding="utf-8")
        for fragment in (
            'output "client_activation_contract"',
            'output "storage_https_uri"',
            'output "substituter_uri"',
            "value       = null",
            'reason                      = "raw-private-gcs-is-not-a-nix-substituter"',
            "signing_key_in_client_scope = false",
        ):
            if fragment not in text:
                errors.append(
                    coded("INTEGRATION", "module does not fail closed for raw storage")
                )
                break

    resources = monorepo / "infra/kubernetes/platform/nix-cache/resources.yaml"
    if not resources.is_file():
        errors.append(coded("INTEGRATION", "source-only Attic resources are missing"))
    else:
        text = resources.read_text(encoding="utf-8")
        required = (
            "replicas: 0",
            "https://nix-cache.invalid/",
            document.get("server", {}).get("amd64_image", "missing-image"),
            "automaticGarbageCollection: disabled",
            "clientSigningKey: forbidden",
            "name: default-deny",
        )
        if any(fragment not in text for fragment in required):
            errors.append(
                coded("INTEGRATION", "source-only Attic resources are not fail closed")
            )

    caller = monorepo / ".github/workflows/nix-cache.yml"
    if document.get("status") == "proposed" and caller.exists():
        errors.append(
            coded("INTEGRATION", "proposed lifecycle must not contain an active caller")
        )
    return sorted(set(errors))


def validate(
    document: dict[str, Any],
    schema: dict[str, Any],
    *,
    root: Path = ROOT,
    monorepo: Path | None = None,
) -> list[str]:
    errors = schema_errors(document, schema)
    errors.extend(policy_errors(document))
    errors.extend(source_errors(root))
    if monorepo is not None:
        errors.extend(integration_errors(document, monorepo))
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monorepo", type=Path)
    parser.add_argument(
        "--require-active",
        action="store_true",
        help="fail unless the reviewed lifecycle is activated",
    )
    args = parser.parse_args()

    document, errors = load_json(CONTRACT, "LOAD")
    schema, schema_load_errors = load_json(SCHEMA, "LOAD")
    errors.extend(schema_load_errors)
    if document is not None and schema is not None:
        errors.extend(
            validate(
                document,
                schema,
                monorepo=args.monorepo.resolve() if args.monorepo else None,
            )
        )
        if args.require_active and document.get("status") != "activated":
            errors.append(coded("ACTIVATION", "lifecycle is not activated"))

    if errors:
        for error in sorted(set(errors)):
            print(error, file=sys.stderr)
        return 1
    assert document is not None
    print(f"Nix binary-cache contract passed (lifecycle: {document['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
