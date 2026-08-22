# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Source-only contract tests for the common CI Bazel cache foundation."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SELECT = load("select_apply_scopes", "scripts/select-apply-scopes.py")
SCOPE = load("terragrunt_scope_bazel_cache", "scripts/terragrunt-scope.py")


class BazelCacheFoundationTest(unittest.TestCase):
    def test_common_ci_cache_is_foundation_owned(self) -> None:
        unit = "5-workloads/ci/bazel-remote-cache"
        self.assertEqual(
            SELECT.scope_for_path(f"{unit}/terragrunt.hcl"), {"foundation"}
        )
        self.assertEqual(
            SCOPE.validate_unit("foundation", unit, SCOPE.SCOPES["foundation"]),
            unit,
        )
        with self.assertRaisesRegex(ValueError, "outside scope development"):
            SCOPE.validate_unit("development", unit, SCOPE.SCOPES["development"])

    def test_identity_authority_has_exact_reader_writer_split(self) -> None:
        automation = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "1-org/automation-iam").glob("*.tf")
        )
        for required in (
            'account_id   = "bazel-cache-reader"',
            'account_id   = "bazel-cache-writer"',
            'resource "google_service_account_iam_member" "bazel_cache_github_wif"',
            'each.key == "pull-request-read" ? "reader" : "writer"',
            'role               = "roles/iam.workloadIdentityUser"',
            'check "bazel_cache_trust_contract"',
            'subject/bazel-cache:${route}',
            "WIF_PROVIDER_BAZEL_CACHE",
            "SA_BAZEL_CACHE_READER",
            "SA_BAZEL_CACHE_WRITER",
        ):
            self.assertIn(required, automation)
        self.assertNotIn("roles/storage.objectAdmin", automation)

    def test_storage_and_key_owners_supply_exact_prerequisites(self) -> None:
        common_projects = (ROOT / "1-org/common-projects/terragrunt.hcl").read_text(
            encoding="utf-8"
        )
        kms = (ROOT / "1-org/kms/terragrunt.hcl").read_text(encoding="utf-8")
        self.assertIn('"storage.googleapis.com"', common_projects)
        self.assertIn("encrypter_decrypters = {", kms)
        self.assertIn(
            'service-${dependency.common_projects.outputs.project_numbers["ci"]}@gs-project-accounts.iam.gserviceaccount.com',
            kms,
        )

    def test_bucket_caller_uses_module_owned_iam_and_access_logs(self) -> None:
        unit = (ROOT / "5-workloads/ci/bazel-remote-cache/terragrunt.hcl").read_text(
            encoding="utf-8"
        )
        for required in (
            'module_version = "v0.4.0"',
            '//bazel_remote_cache?ref=${local.module_version}',
            'project_ids["ci"]',
            'crypto_key_ids["ci_artifacts"]',
            'config_path = "../../shared/bazel-cache-access-logs"',
            "bazel_cache_service_accounts.reader",
            "bazel_cache_service_accounts.writer",
            'access_log_object_prefix = "bazel-remote-cache/common-ci/"',
        ):
            self.assertIn(required, unit)
        self.assertNotIn("google_storage_bucket_iam", unit)

    def test_activation_hold_is_explicit(self) -> None:
        readme = (ROOT / "5-workloads/ci/bazel-remote-cache/README.md").read_text(
            encoding="utf-8"
        )
        gates = (ROOT / "docs/production-activation-gates.md").read_text(
            encoding="utf-8"
        )
        for required in (
            "planned contract `v0.4.0`",
            "does not assert that the tag is published or any resource is live",
            "ordinary `PUT` requests",
            "`ifGenerationMatch=0`",
        ):
            self.assertIn(required, readme)
        self.assertIn("GitHub-hosted Bazel cache", gates)
        self.assertIn("planned module `v0.4.0` is unpublished", gates)


if __name__ == "__main__":
    unittest.main()
