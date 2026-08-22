# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Tests for the fail-closed Nix binary-cache lifecycle contract."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    path = ROOT / "scripts/validate_nix_binary_cache.py"
    spec = importlib.util.spec_from_file_location("validate_nix_binary_cache", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()
SELECT = load("select_apply_scopes_nix_cache", "scripts/select-apply-scopes.py")
SCOPE = load("terragrunt_scope_nix_cache", "scripts/terragrunt-scope.py")
CONTRACT = json.loads((ROOT / "contracts/nix-binary-cache.json").read_text())
SCHEMA = json.loads((ROOT / "contracts/nix-binary-cache.schema.json").read_text())


class NixBinaryCacheTest(unittest.TestCase):
    def test_live_units_are_foundation_owned(self) -> None:
        for unit in (
            "5-workloads/ci/nix-binary-cache",
            "5-workloads/ci/nix-cache-secrets",
        ):
            self.assertEqual(
                SELECT.scope_for_path(f"{unit}/terragrunt.hcl"), {"foundation"}
            )
            self.assertEqual(
                SCOPE.validate_unit("foundation", unit, SCOPE.SCOPES["foundation"]),
                unit,
            )
            with self.assertRaisesRegex(ValueError, "outside scope development"):
                SCOPE.validate_unit("development", unit, SCOPE.SCOPES["development"])

    def test_checked_in_contract_is_proposed_and_fail_closed(self) -> None:
        errors = VALIDATOR.validate(CONTRACT, SCHEMA)
        self.assertEqual(errors, [])
        self.assertEqual(CONTRACT["status"], "proposed")
        self.assertFalse(CONTRACT["client"]["enabled"])
        self.assertFalse(CONTRACT["publication"]["enabled"])
        self.assertIsNone(CONTRACT["client"]["substituter_uri"])
        self.assertIsNone(CONTRACT["client"]["trusted_public_key"])

    def test_proposed_contract_cannot_enable_a_client(self) -> None:
        candidate = copy.deepcopy(CONTRACT)
        candidate["client"]["enabled"] = True
        errors = VALIDATOR.schema_errors(candidate, SCHEMA)
        self.assertTrue(
            any(error.startswith("[NIXCACHE-SCHEMA]") for error in errors), errors
        )

    def test_qualified_contract_still_cannot_enable_a_client(self) -> None:
        candidate = self._qualified_contract()
        self.assertEqual(VALIDATOR.schema_errors(candidate, SCHEMA), [])
        candidate["client"]["enabled"] = True
        errors = VALIDATOR.schema_errors(candidate, SCHEMA)
        self.assertTrue(
            any(error.startswith("[NIXCACHE-SCHEMA]") for error in errors), errors
        )

    def test_qualifying_contract_allows_partial_evidence_but_not_clients(self) -> None:
        candidate = self._qualified_contract()
        candidate["status"] = "qualifying"
        candidate["blockers"] = [VALIDATOR.EXPECTED_BLOCKERS[-1]]
        candidate["evidence"]["signature_tamper"] = False
        candidate["qualification_evidence"] = copy.deepcopy(
            CONTRACT["qualification_evidence"]
        )
        self.assertEqual(VALIDATOR.schema_errors(candidate, SCHEMA), [])
        self.assertEqual(VALIDATOR.policy_errors(candidate), [])
        candidate["client"]["enabled"] = True
        self.assertNotEqual(VALIDATOR.schema_errors(candidate, SCHEMA), [])

    def test_activated_contract_is_valid_after_all_gates(self) -> None:
        candidate = self._qualified_contract()
        candidate["status"] = "activated"
        candidate["client"]["enabled"] = True
        self.assertEqual(VALIDATOR.schema_errors(candidate, SCHEMA), [])

    def test_activated_contract_requires_every_evidence_gate(self) -> None:
        candidate = self._qualified_contract()
        candidate["status"] = "activated"
        candidate["client"]["enabled"] = True
        candidate["evidence"]["signature_tamper"] = False
        errors = VALIDATOR.schema_errors(candidate, SCHEMA)
        self.assertTrue(
            any(error.startswith("[NIXCACHE-SCHEMA]") for error in errors), errors
        )

    def test_secret_detection_is_redacted(self) -> None:
        candidate = copy.deepcopy(CONTRACT)
        secret = "-----BEGIN " + "PRIVATE KEY-----"
        candidate["module"]["path"] = secret
        errors = VALIDATOR.policy_errors(candidate)
        self.assertIn(
            "[NIXCACHE-SECRET] contract contains secret-like material; value is redacted",
            errors,
        )
        self.assertNotIn(secret, "\n".join(errors))

    def test_hmac_resource_is_rejected_without_exposing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in VALIDATOR.REQUIRED_SOURCE_PATHS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            (root / "unsafe.tf").write_text(
                'resource "google_storage_hmac_key" "unsafe" {}', encoding="utf-8"
            )
            errors = VALIDATOR.source_errors(root)
        self.assertIn(
            "[NIXCACHE-SOURCE] GCS HMAC resources are forbidden because their secret enters Terraform state",
            errors,
        )

    def test_require_active_cli_gate_is_machine_readable(self) -> None:
        self.assertEqual(CONTRACT["status"], "proposed")
        self.assertNotEqual(CONTRACT["status"], "activated")

    @staticmethod
    def _qualified_contract() -> dict:
        candidate = copy.deepcopy(CONTRACT)
        candidate["status"] = "qualified"
        candidate["blockers"] = []
        candidate["client"].update(
            {
                "enabled": False,
                "private_read_authentication_qualified": True,
                "substituter_uri": "https://cache.example.invalid/mindclade",
                "trusted_public_key": "mindclade:YWJjZA==",
            }
        )
        for key in candidate["evidence"]:
            candidate["evidence"][key] = True
        candidate["module"]["release_status"] = "published"
        candidate["publication"]["enabled"] = True
        candidate["qualification_evidence"].update(
            {
                "object_generation": "1",
                "object_uri": "gs://mc-production-qualification-evidence/nix-binary-cache/qualification.json",
                "reviewed_at": "2026-08-22T12:00:00Z",
                "reviewer": "security-reviewer",
                "sha256": "sha256:" + "a" * 64,
                "verification_digest": "sha256:" + "b" * 64,
            }
        )
        candidate["server"].update(
            {
                "active_gitops_target": True,
                "endpoint": "https://cache.example.invalid/",
                "replicas": 2,
            }
        )
        return candidate


if __name__ == "__main__":
    unittest.main()
