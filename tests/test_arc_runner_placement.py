# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml


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

    def test_spot_pool_capacity_regressions_are_rejected(self) -> None:
        source = (ROOT / VALIDATE.SPOT_UNIT).read_text(encoding="utf-8")
        raised_floor = source.replace(
            "total_min_nodes   = 0", "total_min_nodes   = 1"
        )
        raised_ceiling = source.replace(
            "total_max_nodes   = 8", "total_max_nodes   = 80"
        )
        self.assertTrue(
            any(
                "zero floor" in error
                for error in VALIDATE.validate_spot_unit_text(raised_floor)
            )
        )
        self.assertTrue(
            any(
                "eight nodes" in error
                for error in VALIDATE.validate_spot_unit_text(raised_ceiling)
            )
        )

    def test_spot_documentation_preserves_qualification_order(self) -> None:
        root = ROOT / "5-workloads/ci/README.md"
        documentation = root.read_text(encoding="utf-8")
        self.assertLess(
            documentation.index("Before applying the Spot pool"),
            documentation.index("Apply the pool only in a controlled qualification window"),
        )
        self.assertLess(
            documentation.index(
                "Apply the pool only in a controlled qualification window"
            ),
            documentation.index("After the pool exists"),
        )
        self.assertLess(
            documentation.index("After the pool exists"),
            documentation.index("then activate the GitOps presubmit consumer"),
        )

    @staticmethod
    def write_gitops_fixture(root: Path) -> None:
        for release in VALIDATE.RUNNER_RELEASES:
            if release == VALIDATE.PRESUBMIT_RELEASE:
                selector = VALIDATE.EXPECTED_SPOT_NODE_SELECTOR
                tolerations = VALIDATE.EXPECTED_SPOT_TOLERATIONS
            else:
                selector = VALIDATE.EXPECTED_ON_DEMAND_NODE_SELECTOR
                tolerations = VALIDATE.EXPECTED_ON_DEMAND_TOLERATIONS
            spec = {"nodeSelector": selector, "tolerations": tolerations}
            values = {"template": {"spec": spec}}
            rendered = {
                "apiVersion": "actions.github.com/v1alpha1",
                "kind": "AutoscalingRunnerSet",
                "spec": {"template": {"spec": spec}},
            }
            for tree, payload in (("values", values), ("rendered", rendered)):
                path = root / f"arc/{tree}/{release}.yaml"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    def test_gitops_contract_separates_spot_from_on_demand_releases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gitops = Path(directory)
            self.write_gitops_fixture(gitops)
            self.assertEqual(VALIDATE.validate_gitops(gitops), [])

            presubmit = gitops / "arc/values/presubmit.yaml"
            payload = yaml.safe_load(presubmit.read_text(encoding="utf-8"))
            payload["template"]["spec"]["nodeSelector"] = (
                VALIDATE.EXPECTED_ON_DEMAND_NODE_SELECTOR
            )
            payload["template"]["spec"]["tolerations"] = (
                VALIDATE.EXPECTED_ON_DEMAND_TOLERATIONS
            )
            presubmit.write_text(yaml.safe_dump(payload), encoding="utf-8")
            errors = VALIDATE.validate_gitops(gitops)
            self.assertTrue(
                any(
                    "presubmit.yaml" in error and "Spot" in error
                    for error in errors
                )
            )

    def test_gitops_presubmit_requires_both_exact_spot_tolerations(self) -> None:
        spec = {
            "nodeSelector": VALIDATE.EXPECTED_SPOT_NODE_SELECTOR,
            "tolerations": VALIDATE.EXPECTED_SPOT_TOLERATIONS[1:],
        }
        errors = VALIDATE.validate_runner_spec(
            Path("presubmit.yaml"), "presubmit", spec
        )
        self.assertEqual(
            errors,
            ["presubmit.yaml disagrees with the ARC presubmit Spot pool node taints"],
        )

    def test_gitops_contract_requires_both_presubmit_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gitops = Path(directory)
            self.write_gitops_fixture(gitops)
            (gitops / "arc/values/presubmit.yaml").unlink()
            (gitops / "arc/rendered/presubmit.yaml").unlink()
            errors = VALIDATE.validate_gitops(gitops)
            self.assertTrue(
                any("arc/values/presubmit.yaml" in error for error in errors)
            )
            self.assertTrue(
                any("arc/rendered/presubmit.yaml" in error for error in errors)
            )


if __name__ == "__main__":
    unittest.main()
