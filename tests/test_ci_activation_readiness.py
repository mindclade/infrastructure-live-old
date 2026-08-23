# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ci_readiness", ROOT / "scripts/validate-ci-activation-readiness.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CiActivationReadinessTest(unittest.TestCase):
    def test_reviewed_source_is_fail_closed(self) -> None:
        document = MODULE.load_contract()
        self.assertEqual(MODULE.validate(document, dt.date(2026, 8, 23)), [])
        self.assertTrue(all(item["activationState"] == "blocked" for item in document["capabilities"]))

    def test_partial_evidence_is_rejected(self) -> None:
        document = copy.deepcopy(MODULE.load_contract())
        document["capabilities"][0]["qualifiedAt"] = "2026-08-23T00:00:00Z"
        errors = MODULE.validate(document, dt.date(2026, 8, 23))
        self.assertTrue(any("incomplete" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
