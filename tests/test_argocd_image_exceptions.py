#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Mutation tests for the Argo exact-digest Binary Authorization contract."""

from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_argocd_image_exceptions",
    ROOT / "scripts/validate-argocd-image-exceptions.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)


class ArgoImageExceptionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(
            (ROOT / "contracts/argocd-image-exceptions.json").read_text("utf-8")
        )

    def errors(self, value: dict) -> list[str]:
        return VALIDATE.validate_contract(value, dt.date(2026, 8, 20))

    def test_repository_contract_passes(self) -> None:
        self.assertEqual(self.errors(self.contract), [])

    def test_wildcard_or_tag_fails(self) -> None:
        for image in ("quay.io/argoproj/*", "quay.io/argoproj/argocd:v3.5.1"):
            with self.subTest(image=image):
                value = copy.deepcopy(self.contract)
                value["exceptions"][0]["image"] = image
                self.assertTrue(self.errors(value))

    def test_expired_or_overlong_exception_fails(self) -> None:
        for granted, expires in (
            ("2025-01-01", "2025-03-01"),
            ("2026-08-20", "2026-11-19"),
        ):
            with self.subTest(granted=granted, expires=expires):
                value = copy.deepcopy(self.contract)
                value["exceptions"][0]["granted"] = granted
                value["exceptions"][0]["expires"] = expires
                self.assertTrue(self.errors(value))

    def test_missing_security_approval_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["exceptions"][0]["approval"] = "pending"
        self.assertTrue(self.errors(value))

    def test_extra_or_missing_image_fails(self) -> None:
        for mutate in ("extra", "missing"):
            with self.subTest(mutate=mutate):
                value = copy.deepcopy(self.contract)
                if mutate == "extra":
                    value["exceptions"].append(copy.deepcopy(value["exceptions"][0]))
                    value["exceptions"][-1]["image"] = (
                        "example.invalid/extra@sha256:" + "f" * 64
                    )
                else:
                    value["exceptions"].pop()
                self.assertTrue(self.errors(value))

    def test_live_policy_has_no_bypass_and_enforces_staging(self) -> None:
        live = "\n".join(
            (
                ROOT
                / f"5-workloads/{environment}/binary-authorization/terragrunt.hcl"
            ).read_text("utf-8")
            for environment in ("development", "staging", "production")
        )
        self.assertNotIn("cluster_admission_rules", live)
        self.assertNotIn("ALWAYS_ALLOW", live)
        defaults = (ROOT / "_envcommon/binauthz.hcl").read_text("utf-8")
        self.assertIn(
            'local.environment == "development" ? "DRYRUN_AUDIT_LOG_ONLY" : "ENFORCED_BLOCK_AND_AUDIT_LOG"',
            defaults,
        )
        self.assertIn("exempt_images", defaults)
        for wildcard in ("/*", "/**"):
            self.assertNotIn(wildcard, defaults)


if __name__ == "__main__":
    unittest.main()
