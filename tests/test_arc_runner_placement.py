# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_arc_runner_placement",
    ROOT / "scripts/validate-arc-runner-placement.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)


class ArcRunnerPlacementTest(unittest.TestCase):
    def test_infrastructure_contract_passes(self) -> None:
        self.assertEqual(VALIDATE.validate_infrastructure(ROOT), [])

    def test_missing_taint_is_rejected(self) -> None:
        path = ROOT / VALIDATE.RUNNER_UNIT
        source = path.read_text(encoding="utf-8")
        source = source.replace(
            'key    = "scheduling.mindclade.dev/arc-runner"',
            'key    = "scheduling.mindclade.dev/other"',
        )
        errors = VALIDATE.validate_runner_unit_text(source)
        self.assertTrue(any("scheduling taint" in error for error in errors), errors)

    def test_capacity_regression_is_rejected(self) -> None:
        path = ROOT / VALIDATE.RUNNER_UNIT
        source = path.read_text(encoding="utf-8")
        source = source.replace("total_max_nodes   = 6", "total_max_nodes   = 60")
        errors = VALIDATE.validate_runner_unit_text(source)
        self.assertTrue(any("ceiling" in error for error in errors), errors)

    def test_spot_pool_cannot_overlap_active_runner_class(self) -> None:
        source = (ROOT / VALIDATE.SPOT_UNIT).read_text(encoding="utf-8")
        source = source.replace('"arc-presubmit-spot"', '"arc-runner"')
        errors = VALIDATE.validate_spot_unit_text(source)
        self.assertTrue(any("isolated" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
