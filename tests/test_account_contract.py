# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Regression tests for the deployed bootstrap 1.2 account contract."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_HCL = ROOT / "account.hcl"
SPEC = importlib.util.spec_from_file_location(
    "validate_account", ROOT / "scripts/validate-account.py"
)
assert SPEC is not None and SPEC.loader is not None
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)


class AccountContractTest(unittest.TestCase):
    def test_source_contract_is_complete_without_runtime_credentials(self) -> None:
        self.assertEqual(VALIDATE.source_errors(), [])

    def test_deferred_v4_identity_inputs_are_absent(self) -> None:
        text = ACCOUNT_HCL.read_text(encoding="utf-8")
        self.assertNotIn("ARTIFACT_RELEASE_IDENTITIES_JSON", text)
        self.assertNotIn("DR_EVIDENCE_IDENTITY_JSON", text)
        self.assertNotIn("WIF_PROVIDER_ARC", text)

    def test_v3_signer_tuple_is_required(self) -> None:
        text = ACCOUNT_HCL.read_text(encoding="utf-8")
        for name in (
            "WIF_PROVIDER_SIGNER",
            "ARTIFACT_SIGNER_PRINCIPAL",
            "ARTIFACT_SIGNER_JOB_WORKFLOW_REF",
        ):
            self.assertIn(f'get_env("{name}")', text)

    def test_buildkite_defaults_fail_closed(self) -> None:
        text = ACCOUNT_HCL.read_text(encoding="utf-8")
        self.assertIn('get_env("BUILDKITE_WIF_ENABLED", "false")', text)
        self.assertIn('get_env("BUILDKITE_WIF_POOL_NAME", "")', text)
        self.assertEqual(VALIDATE.buildkite_errors("false", ""), [])
        self.assertTrue(
            VALIDATE.buildkite_errors(
                "false",
                "projects/123/locations/global/workloadIdentityPools/buildkite",
            )
        )


if __name__ == "__main__":
    unittest.main()
