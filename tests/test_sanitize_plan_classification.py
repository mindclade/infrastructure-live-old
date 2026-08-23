# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sanitize_plan", ROOT / "scripts/sanitize-plan-classification.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SanitizedPlanClassificationTest(unittest.TestCase):
    def test_resource_metadata_is_removed(self) -> None:
        source = {
            "summary": {"create": 1, "update": 0, "delete": 1, "replace": 0, "read": 0, "no-op": 0},
            "destructive": True,
            "critical": True,
            "critical_destructive": True,
            "plan_files": ["secret/path.json"],
            "destructive_changes": [{"address": "secret.address"}],
            "critical_changes": [{"address": "secret.address"}],
        }
        result = MODULE.sanitize(source, "a" * 40)
        self.assertEqual(result["risk"]["destructiveChangeCount"], 1)
        self.assertNotIn("secret", str(result))


if __name__ == "__main__":
    unittest.main()
