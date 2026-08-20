#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Safety tests for infrastructure planning operators."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHANGED = load("plan_changed", "scripts/plan-changed.py")
SCOPE = load("terragrunt_scope", "scripts/terragrunt-scope.py")
ACCOUNT = load("bootstrap_account", "scripts/bootstrap-account.py")
ACCOUNT_VALIDATOR = load("validate_account", "scripts/validate-account.py")
STATE_PREFIX = load("classify_state_prefix", "scripts/classify-state-prefix.py")


class PlanSafetyTest(unittest.TestCase):
    def test_repository_root_is_never_a_plan_directory(self) -> None:
        with self.assertRaises(ValueError):
            SCOPE.validated_plan_path(ROOT)

    def test_temporary_child_is_an_allowed_plan_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "plans" / "development"
            self.assertEqual(SCOPE.validated_plan_path(candidate), candidate.resolve())

    def test_checksum_manifest_detects_tampering_and_extra_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "plan.tfplan").write_text("first", encoding="utf-8")
            SCOPE.write_checksums(bundle)
            SCOPE.verify_checksums(bundle)
            (bundle / "plan.tfplan").write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                SCOPE.verify_checksums(bundle)

    def test_dependent_closure_is_order_independent(self) -> None:
        selected = {Path("a")}
        dependencies = {Path("c"): {Path("b")}, Path("b"): {Path("a")}}
        CHANGED.dependent_closure(selected, dependencies)
        self.assertEqual(selected, {Path("a"), Path("b"), Path("c")})

    def test_unit_traversal_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SCOPE.validate_unit(
                "development", "../outside", SCOPE.SCOPES["development"]
            )

    def test_customer_id_must_be_explicit_and_well_formed(self) -> None:
        with self.assertRaises(ValueError):
            ACCOUNT.validated_customer_id("")
        self.assertEqual(ACCOUNT.validated_customer_id("C01234567"), "C01234567")

    def test_disabled_buildkite_contract_requires_null_resources(self) -> None:
        self.assertEqual(
            ACCOUNT.validated_buildkite(
                {
                    "enabled": False,
                    "workload_identity_pool": None,
                    "workload_identity_provider": None,
                },
                "123456789",
            ),
            (False, None),
        )
        with self.assertRaises(ValueError):
            ACCOUNT.validated_buildkite(
                {
                    "enabled": False,
                    "workload_identity_pool": "projects/123456789/locations/global/workloadIdentityPools/buildkite",
                    "workload_identity_provider": None,
                },
                "123456789",
            )

    def test_enabled_buildkite_contract_requires_exact_pool_and_provider(self) -> None:
        pool = "projects/123456789/locations/global/workloadIdentityPools/buildkite"
        self.assertEqual(
            ACCOUNT.validated_buildkite(
                {
                    "enabled": True,
                    "workload_identity_pool": pool,
                    "workload_identity_provider": f"{pool}/providers/buildkite",
                },
                "123456789",
            ),
            (True, pool),
        )
        with self.assertRaises(ValueError):
            ACCOUNT.validated_buildkite(
                {
                    "enabled": True,
                    "workload_identity_pool": pool,
                    "workload_identity_provider": None,
                },
                "123456789",
            )

    def test_runtime_buildkite_validation_is_mode_aware(self) -> None:
        pool = "projects/123456789/locations/global/workloadIdentityPools/buildkite"
        self.assertEqual(ACCOUNT_VALIDATOR.buildkite_errors("false", ""), [])
        self.assertEqual(ACCOUNT_VALIDATOR.buildkite_errors("true", pool), [])
        self.assertTrue(ACCOUNT_VALIDATOR.buildkite_errors("false", pool))
        self.assertTrue(ACCOUNT_VALIDATOR.buildkite_errors("true", ""))
        self.assertTrue(ACCOUNT_VALIDATOR.buildkite_errors("yes", ""))

    def test_state_prefix_accepts_only_exact_no_object_result(self) -> None:
        self.assertEqual(STATE_PREFIX.classify(0, ""), "existing-or-empty")
        self.assertEqual(
            STATE_PREFIX.classify(1, f"{STATE_PREFIX.NO_OBJECTS}\n"), "fresh"
        )
        for status, stderr in (
            (1, "ERROR: permission denied\n"),
            (1, f"warning\n{STATE_PREFIX.NO_OBJECTS}\n"),
            (2, f"{STATE_PREFIX.NO_OBJECTS}\n"),
            (0, "warning\n"),
        ):
            with self.subTest(status=status, stderr=stderr):
                with self.assertRaises(ValueError):
                    STATE_PREFIX.classify(status, stderr)


class ImportRuntimeContractTest(unittest.TestCase):
    def test_every_provider_lock_uses_terraform_115_normalized_constraints(self) -> None:
        locks = sorted(ROOT.rglob(".terraform.lock.hcl"))
        self.assertEqual(len(locks), 103)
        for lock in locks:
            text = lock.read_text(encoding="utf-8")
            self.assertEqual(text.count('constraints = "7.41.0"'), 2, lock)
            self.assertEqual(text.count('"h1:'), 4, lock)
            self.assertNotIn('constraints = "= 7.41.0"', text, lock)

    def test_both_nix_shells_pin_terragrunt_to_terraform(self) -> None:
        flake = (ROOT / "flake.nix").read_text(encoding="utf-8")
        self.assertEqual(
            flake.count('TG_TF_PATH = "${terraform-pinned}/bin/terraform";'), 2
        )

    def test_baseline_only_skips_the_folders_state_dependency(self) -> None:
        policy = (ROOT / "1-org/org-policies/terragrunt.hcl").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'baseline_org_policy_adoption = get_env("ORG_POLICY_ACTIVATION_PHASE", "") == "baseline"',
            policy,
        )
        self.assertIn(
            "skip_outputs = local.baseline_org_policy_adoption", policy
        )
        self.assertIn(
            "mock_outputs = local.baseline_org_policy_adoption ? {", policy
        )
        self.assertNotIn("skip_outputs = true", policy)


if __name__ == "__main__":
    unittest.main()
