# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_protected_run", ROOT / "scripts/validate-protected-run.py"
)
assert SPEC is not None and SPEC.loader is not None
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)

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

    def test_apply_workflow_enforces_guard_order_and_active_apply_safety(self) -> None:
        workflow = (ROOT / ".github/workflows/apply.yml").read_text(encoding="utf-8")
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("source_rollback:", workflow)
        self.assertIn("protected-run.json", workflow)
        plan, apply = workflow.split("\n  apply:\n", 1)
        self.assertLess(plan.index("check-source"), plan.index("google-github-actions/auth@"))
        self.assertGreaterEqual(apply.count("validate-plan"), 2)
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


if __name__ == "__main__":
    unittest.main()
