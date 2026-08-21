# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate-workload-identity-contract.py"
SPEC = importlib.util.spec_from_file_location("workload_identity_contract", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


class WorkloadIdentityContractTest(unittest.TestCase):
    def test_live_identity_and_holdout_contract_is_typed(self) -> None:
        ref, errors = CONTRACT.live_contract()
        self.assertEqual(ref, "v0.4.0")
        self.assertEqual(errors, [])
        self.assertEqual(len(CONTRACT.IDENTITIES), 4)
        self.assertEqual(
            CONTRACT.IDENTITIES["holdout_evaluator"]["namespace"],
            "mindclade-evaluation",
        )

    def test_kubernetes_contract_rejects_missing_environment_binding(self) -> None:
        base = "\n---\n".join(
            "kind: ServiceAccount\nmetadata:\n"
            f"  name: {contract['ksa_name']}\n"
            f"  namespace: {contract['namespace']}"
            for contract in CONTRACT.IDENTITIES.values()
        )
        overlay = "\n".join(
            f"value: {contract['account_id']}@mc-production-research.iam.gserviceaccount.com\n"
            "value: no-api-token-workload-identity"
            for contract in CONTRACT.IDENTITIES.values()
        )
        documents = {
            "infra/kubernetes/base/service-accounts.yaml": base,
            "infra/kubernetes/overlays/production/kustomization.yaml": overlay.replace(
                "training-b200@mc-production-research.iam.gserviceaccount.com",
                "missing@example.invalid",
            ),
        }
        errors = CONTRACT.kubernetes_contract_errors(
            "production", documents.__getitem__
        )
        self.assertTrue(any("training_b200" in error for error in errors))

    def test_evaluator_is_not_a_holdout_deny_principal(self) -> None:
        self.assertNotIn("holdout_evaluator", CONTRACT.DENIED_IDENTITIES)
        self.assertEqual(len(CONTRACT.DENIED_IDENTITIES), 3)


if __name__ == "__main__":
    unittest.main()
