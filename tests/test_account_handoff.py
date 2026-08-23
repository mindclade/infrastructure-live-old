#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Behavioral tests for the applied bootstrap account handoff."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "account_handoff", ROOT / "scripts/account_handoff.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HANDOFF = load_module()


def account_values() -> dict[str, str]:
    return {
        "STATE_LOCATION": "US",
        "TFSTATE_BUCKET_DEVELOPMENT": "mc-state-development",
        "TFSTATE_BUCKET_STAGING": "mc-state-staging",
        "TFSTATE_BUCKET_PRODUCTION": "mc-state-production",
        "SA_TF_LIVE_PLAN": "tf-live-plan@mc-ci.iam.gserviceaccount.com",
        "SA_TF_LIVE_APPLY_FOUNDATION": (
            "tf-live-foundation@mc-ci.iam.gserviceaccount.com"
        ),
        "SA_TF_LIVE_APPLY_DEVELOPMENT": (
            "tf-live-development@mc-ci.iam.gserviceaccount.com"
        ),
        "SA_TF_LIVE_APPLY_STAGING": (
            "tf-live-staging@mc-ci.iam.gserviceaccount.com"
        ),
        "SA_TF_LIVE_APPLY_PRODUCTION": (
            "tf-live-production@mc-ci.iam.gserviceaccount.com"
        ),
    }


def platform_contract() -> dict[str, object]:
    return {
        "contract_version": "2.0.0",
        "organization_id": "123456789",
        "state": {"primary_location": "US"},
    }


class AccountHandoffTest(unittest.TestCase):
    def build(self) -> tuple[dict[str, str], dict[str, object]]:
        values = account_values()
        record = HANDOFF.build_account_handoff(
            platform_contract(), values, "a" * 40
        )
        return values, record

    def test_generated_record_satisfies_schema_and_runtime_parity(self) -> None:
        values, record = self.build()
        schema = json.loads(HANDOFF.SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(record)
        self.assertEqual(
            HANDOFF.account_handoff_errors(
                json.dumps(record, sort_keys=True, separators=(",", ":")), values
            ),
            [],
        )

    def test_production_bucket_and_service_account_mismatches_are_redacted(
        self,
    ) -> None:
        values, record = self.build()
        values["TFSTATE_BUCKET_PRODUCTION"] = "redacted-production-bucket"
        values["SA_TF_LIVE_APPLY_PRODUCTION"] = (
            "redacted-production@mc-ci.iam.gserviceaccount.com"
        )
        errors = HANDOFF.account_handoff_errors(json.dumps(record), values)
        self.assertIn(
            "[ACCOUNT-HANDOFF-MISMATCH] TFSTATE_BUCKET_PRODUCTION differs from bootstrap output",
            errors,
        )
        self.assertIn(
            "[ACCOUNT-HANDOFF-MISMATCH] SA_TF_LIVE_APPLY_PRODUCTION differs from bootstrap output",
            errors,
        )
        self.assertNotIn(values["TFSTATE_BUCKET_PRODUCTION"], "\n".join(errors))
        self.assertNotIn(
            values["SA_TF_LIVE_APPLY_PRODUCTION"], "\n".join(errors)
        )

    def test_extra_and_stale_fields_fail_exactly(self) -> None:
        values, record = self.build()
        stale = copy.deepcopy(record)
        stale["state_buckets"]["retired"] = "mc-state-retired"
        errors = HANDOFF.account_handoff_errors(json.dumps(stale), values)
        self.assertIn(
            "[ACCOUNT-HANDOFF-SCHEMA] bootstrap account handoff violates its schema",
            errors,
        )
        self.assertIn(
            "[ACCOUNT-HANDOFF-SHAPE] bootstrap state_buckets inventory is not exact",
            errors,
        )

    def test_invalid_json_and_versions_have_stable_codes(self) -> None:
        values, record = self.build()
        self.assertEqual(
            HANDOFF.account_handoff_errors("not-json", values),
            ["[ACCOUNT-HANDOFF-JSON] bootstrap account handoff is not valid JSON"],
        )
        record["schema_version"] = 2
        errors = HANDOFF.account_handoff_errors(json.dumps(record), values)
        self.assertIn(
            "[ACCOUNT-HANDOFF-VERSION] bootstrap account handoff version differs",
            errors,
        )

    def test_export_requires_clean_full_commit(self) -> None:
        clean = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        revision = subprocess.CompletedProcess(
            [], 0, stdout=f"{'b' * 40}\n", stderr=""
        )
        with mock.patch.object(HANDOFF.subprocess, "run", side_effect=[clean, revision]):
            self.assertEqual(HANDOFF.bootstrap_source_commit(ROOT), "b" * 40)

        dirty = subprocess.CompletedProcess(
            [], 0, stdout=" M outputs.tf\n", stderr=""
        )
        with mock.patch.object(HANDOFF.subprocess, "run", return_value=dirty):
            with self.assertRaisesRegex(ValueError, "changes or untracked files"):
                HANDOFF.bootstrap_source_commit(ROOT)

    def test_all_connected_workflows_map_the_canonical_record(self) -> None:
        mapping = (
            "BOOTSTRAP_ACCOUNT_HANDOFF_JSON: "
            "${{ vars.BOOTSTRAP_ACCOUNT_HANDOFF_JSON }}"
        )
        for path in (
            ".github/workflows/apply.yml",
            ".github/workflows/cost.yml",
            ".github/workflows/drift.yml",
            ".github/workflows/plan.yml",
        ):
            with self.subTest(path=path):
                self.assertIn(mapping, (ROOT / path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
