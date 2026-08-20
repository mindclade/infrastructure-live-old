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


if __name__ == "__main__":
    unittest.main()
