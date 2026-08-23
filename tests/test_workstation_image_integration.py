# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_workstation_image_integration",
    ROOT / "scripts/validate-workstation-image-integration.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)

INFRASTRUCTURE = json.loads(
    (ROOT / "contracts/workstation-egress.json").read_text(encoding="utf-8")
)
GITOPS = {
    "spec": {
        "state": "qualifying",
        "authority": copy.deepcopy(VALIDATE.EXPECTED_AUTHORITY),
        "releases": copy.deepcopy(INFRASTRUCTURE["releases"]),
        "sourceGates": {
            "imageContractValidated": True,
            "runtimeFetchesAbsent": True,
            "createOnlyPublicationContract": True,
            "terraformImageAuthoritySeparated": True,
            "governedSourceEvidenceTransition": True,
        },
        "connectedGates": {"sourceObjectPublished": False},
        "activation": copy.deepcopy(VALIDATE.EXPECTED_ACTIVATION),
    }
}


class WorkstationImageIntegrationTest(unittest.TestCase):
    def test_release_and_authority_contract_passes(self) -> None:
        self.assertEqual(VALIDATE.validation_errors(INFRASTRUCTURE, GITOPS), [])

    def test_release_drift_is_rejected(self) -> None:
        candidate = copy.deepcopy(GITOPS)
        candidate["spec"]["releases"]["workflowContract"] = "v6.0.0"
        errors = VALIDATE.validation_errors(INFRASTRUCTURE, candidate)
        self.assertIn(
            "GitOps workstation releases differ from infrastructure", errors
        )

    def test_authority_drift_is_rejected(self) -> None:
        candidate = copy.deepcopy(GITOPS)
        candidate["spec"]["authority"]["gitopsRole"] = "resource-owner"
        errors = VALIDATE.validation_errors(INFRASTRUCTURE, candidate)
        self.assertTrue(any("authority boundary" in error for error in errors), errors)

    def test_uncoordinated_connected_claim_is_rejected(self) -> None:
        candidate = copy.deepcopy(GITOPS)
        candidate["spec"]["connectedGates"]["sourceObjectPublished"] = True
        errors = VALIDATE.validation_errors(INFRASTRUCTURE, candidate)
        self.assertIn("GitOps workstation connected gates must remain false", errors)


if __name__ == "__main__":
    unittest.main()
