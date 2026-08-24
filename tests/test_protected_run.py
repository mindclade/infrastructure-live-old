# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_protected_run", ROOT / "scripts/validate-protected-run.py"
)
assert SPEC is not None and SPEC.loader is not None
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)
SCOPE_SPEC = importlib.util.spec_from_file_location(
    "terragrunt_scope_for_protected_run", ROOT / "scripts/terragrunt-scope.py"
)
assert SCOPE_SPEC is not None and SCOPE_SPEC.loader is not None
SCOPE = importlib.util.module_from_spec(SCOPE_SPEC)
SCOPE_SPEC.loader.exec_module(SCOPE)

CURRENT = "a" * 40
OLDER = "b" * 40


class ProtectedRunTest(unittest.TestCase):
    def test_current_head_is_selected(self) -> None:
        self.assertEqual(
            GUARD.resolve_source(
                event_name="push",
                event_ref="refs/heads/main",
                event_sha=CURRENT,
                default_branch="main",
                default_head_sha=CURRENT,
                source_rollback=False,
                source_rollback_sha="",
                change_reference="",
                is_ancestor=lambda _older, _newer: False,
            ),
            (CURRENT, "current"),
        )

    def test_stale_workflow_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(GUARD.GuardError, "current default-branch head"):
            GUARD.resolve_source(
                event_name="workflow_dispatch",
                event_ref="refs/heads/main",
                event_sha=OLDER,
                default_branch="main",
                default_head_sha=CURRENT,
                source_rollback=False,
                source_rollback_sha="",
                change_reference="",
                is_ancestor=lambda _older, _newer: True,
            )

    def test_reviewed_ancestor_rollback_is_selected(self) -> None:
        self.assertEqual(
            GUARD.resolve_source(
                event_name="workflow_dispatch",
                event_ref="refs/heads/main",
                event_sha=CURRENT,
                default_branch="main",
                default_head_sha=CURRENT,
                source_rollback=True,
                source_rollback_sha=OLDER,
                change_reference="INC-1234",
                is_ancestor=lambda older, newer: (older, newer) == (OLDER, CURRENT),
            ),
            (OLDER, "rollback"),
        )

    def test_rollback_without_dispatch_or_change_reference_is_rejected(self) -> None:
        for event_name, change_reference in (("push", "INC-1234"), ("workflow_dispatch", "")):
            with self.subTest(event_name=event_name, change_reference=change_reference):
                with self.assertRaises(GUARD.GuardError):
                    GUARD.resolve_source(
                        event_name=event_name,
                        event_ref="refs/heads/main",
                        event_sha=CURRENT,
                        default_branch="main",
                        default_head_sha=CURRENT,
                        source_rollback=True,
                        source_rollback_sha=OLDER,
                        change_reference=change_reference,
                        is_ancestor=lambda _older, _newer: True,
                    )

    def test_stale_plan_metadata_is_rejected(self) -> None:
        now = 1_000_000
        payload = {
            "schema_version": 1,
            "repository": "mindclade/example",
            "run_id": "123",
            "event_sha": CURRENT,
            "target_sha": CURRENT,
            "default_head_sha": CURRENT,
            "mode": "current",
            "created_at_epoch": now - GUARD.MAXIMUM_PLAN_AGE_SECONDS - 1,
            "maximum_age_seconds": GUARD.MAXIMUM_PLAN_AGE_SECONDS,
        }
        with self.assertRaisesRegex(GUARD.GuardError, "six-hour maximum"):
            GUARD.validate_metadata(
                payload,
                repository="mindclade/example",
                run_id="123",
                event_sha=CURRENT,
                expected_target_sha=CURRENT,
                expected_default_head_sha=CURRENT,
                expected_mode="current",
                now=now,
            )

    def test_protected_metadata_is_bound_into_plan_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "plan.tfplan").write_text("immutable plan", encoding="utf-8")
            SCOPE.write_checksums(bundle)
            metadata = b'{"schema_version": 1}\n'
            (bundle / GUARD.PROTECTED_RUN_METADATA).write_bytes(metadata)
            digest = hashlib.sha256(metadata).hexdigest()
            (bundle / GUARD.PROTECTED_RUN_CHECKSUM).write_text(
                f"{digest}  {GUARD.PROTECTED_RUN_METADATA}\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "exact contents"):
                SCOPE.verify_checksums(bundle)
            GUARD.bind_plan(bundle)
            SCOPE.verify_checksums(bundle)

            (bundle / GUARD.PROTECTED_RUN_METADATA).write_bytes(b"tampered\n")
            with self.assertRaisesRegex(ValueError, "exact contents"):
                SCOPE.verify_checksums(bundle)

    def test_plan_binding_rejects_invalid_protected_metadata_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "plan.tfplan").write_text("immutable plan", encoding="utf-8")
            SCOPE.write_checksums(bundle)
            (bundle / GUARD.PROTECTED_RUN_METADATA).write_text(
                "{}\n", encoding="utf-8"
            )
            (bundle / GUARD.PROTECTED_RUN_CHECKSUM).write_text(
                f"{'0' * 64}  {GUARD.PROTECTED_RUN_METADATA}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(GUARD.GuardError, "checksum is invalid"):
                GUARD.bind_plan(bundle)

    def test_apply_workflow_enforces_guard_order_and_active_apply_safety(self) -> None:
        workflow = (ROOT / ".github/workflows/apply.yml").read_text(encoding="utf-8")
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("source_rollback:", workflow)
        self.assertIn("protected-run.json", workflow)
        plan, apply = workflow.split("\n  apply:\n", 1)
        self.assertLess(plan.index("check-source"), plan.index("google-github-actions/auth@"))
        self.assertLess(plan.index("record-plan"), plan.index("bind-plan"))
        self.assertLess(plan.index("bind-plan"), plan.index("actions/upload-artifact@"))
        self.assertGreaterEqual(apply.count("validate-plan"), 2)
        self.assertLess(
            apply.index("verify-plan"), apply.index("google-github-actions/auth@")
        )
        self.assertLess(apply.index("validate-plan"), apply.index("google-github-actions/auth@"))
        mutation = next(
            marker
            for marker in (
                "terraform apply -input=false",
                "scripts/terragrunt-scope.py apply",
            )
            if marker in apply
        )
        self.assertLess(apply.rindex("validate-plan"), apply.index(mutation))

    def test_migration_documentation_rejects_pre_guard_runs(self) -> None:
        documentation = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("does not retrofit a workflow run", documentation)
        self.assertIn("cancel every pre-guard protected run", documentation)
        self.assertIn("Never approve an older", documentation)


if __name__ == "__main__":
    unittest.main()
