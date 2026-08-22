# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_security_txt.py"
SPEC = importlib.util.spec_from_file_location("validate_security_txt", MODULE_PATH)
assert SPEC and SPEC.loader
security_txt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(security_txt)
ROOT = MODULE_PATH.parents[1]


class SecurityTxtTest(unittest.TestCase):
    def test_contract_and_generated_files_are_current(self) -> None:
        contract = security_txt.load_contract(ROOT / "contracts/security-txt.json")
        security_txt.validate_contract(contract, dt.date(2026, 8, 21))
        self.assertEqual(security_txt.validate_outputs(contract, ROOT), [])
        for domain in security_txt.EXPECTED_DOMAINS:
            rendered = security_txt.render(contract, domain)
            self.assertIn("Contact: mailto:security@mindclade.com", rendered)
            self.assertIn(f"Canonical: https://{domain}/.well-known/security.txt", rendered)
            self.assertIn("Policy: https://mindclade.com/security", rendered)

    def test_expired_or_overlong_expiry_fails(self) -> None:
        contract = security_txt.load_contract(ROOT / "contracts/security-txt.json")
        expired = copy.deepcopy(contract)
        expired["expires"] = "2026-09-01T00:00:00Z"
        with self.assertRaisesRegex(security_txt.SecurityTxtError, "renewal window"):
            security_txt.validate_contract(expired, dt.date(2026, 8, 21))
        overlong = copy.deepcopy(contract)
        overlong["expires"] = "2028-01-01T00:00:00Z"
        with self.assertRaisesRegex(security_txt.SecurityTxtError, "366 days"):
            security_txt.validate_contract(overlong, dt.date(2026, 8, 21))

    def test_publication_claim_requires_connected_evidence(self) -> None:
        contract = security_txt.load_contract(ROOT / "contracts/security-txt.json")
        contract["publication"]["status"] = "published"
        with self.assertRaisesRegex(security_txt.SecurityTxtError, "connected evidence"):
            security_txt.validate_contract(contract, dt.date(2026, 8, 21))


if __name__ == "__main__":
    unittest.main()
