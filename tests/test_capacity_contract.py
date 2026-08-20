# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_capacity_contract", ROOT / "scripts/validate-capacity-contract.py"
)
assert SPEC is not None and SPEC.loader is not None
CAPACITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPACITY)


def source(profile: str, code: str) -> dict[str, str]:
    domain = f"mindclade-training-{code}"
    return {
        "infra/kubernetes/base/namespace.yaml": f"name: {domain}\n",
        "infra/kubernetes/platform/gpu/resources.yaml": (
            f"  {code}Profile: {profile}\n"
        ),
        "infra/kubernetes/platform/kueue/resources.yaml": (
            f"name: mindclade-{code}\n"
            f"    mindclade.dev/gpu-profile: {profile}\n"
            f"name: {domain}\nnamespace: {domain}\n"
        ),
        "infra/kubernetes/platform/qualification/kustomization.yaml": (
            f"  - {code}-job.json\n"
        ),
        f"infra/kubernetes/platform/qualification/{code}-job.json": (
            f'"mindclade.dev/gpu-profile": "{profile}"\n"{code}"\n'
        ),
        f"infra/kubernetes/workloads/training/overlays/{code}/kustomization.yaml": (
            f"namespace: {domain}\nvalue: {profile}\nvalue: {domain}\n"
        ),
    }


class CapacityContractTests(unittest.TestCase):
    def write_live_contract(self, root: Path, second_profile: str) -> None:
        common = root / "_envcommon/gpu-nodepool.hcl"
        common.parent.mkdir(parents=True)
        common.write_text(
            'locals {\n  module_version = "v0.4.0"\n}\n', encoding="utf-8"
        )
        for environment in CAPACITY.ENVIRONMENTS:
            for pool, profile in {
                "gpu-a3": "gke-h100-a3-megagpu-8g",
                "gpu-a4": second_profile,
            }.items():
                path = root / f"5-workloads/{environment}/nodepools/{pool}/terragrunt.hcl"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    f'inputs = {{\n  profile = "{profile}"\n}}\n',
                    encoding="utf-8",
                )

    def test_matching_profile_contract_passes(self) -> None:
        profile = "gke-h200-a3-ultragpu-8g"
        documents = source(profile, "h200")
        self.assertEqual(
            CAPACITY.contract_errors({profile}, lambda path: documents[path]), []
        )

    def test_stale_b200_contract_is_rejected_for_h200_live_pool(self) -> None:
        live = "gke-h200-a3-ultragpu-8g"
        documents = source("gke-b200-a4-highgpu-8g", "b200")

        def read(path: str) -> str:
            try:
                return documents[path]
            except KeyError as exc:
                raise RuntimeError("missing") from exc

        errors = CAPACITY.contract_errors({live}, read)
        self.assertTrue(any("differ from live Terraform profiles" in item for item in errors))

    def test_missing_qualification_source_is_rejected(self) -> None:
        profile = "gke-h100-a3-megagpu-8g"
        documents = source(profile, "h100")
        del documents["infra/kubernetes/platform/qualification/h100-job.json"]

        def read(path: str) -> str:
            try:
                return documents[path]
            except KeyError as exc:
                raise RuntimeError("missing") from exc

        errors = CAPACITY.contract_errors({profile}, read)
        self.assertTrue(any("h100-job.json: missing" in item for item in errors))

    def test_live_contract_rejects_b200_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_live_contract(root, "gke-b200-a4-highgpu-8g")
            previous = CAPACITY.ROOT
            CAPACITY.ROOT = root
            try:
                _, _, errors = CAPACITY.live_contract()
            finally:
                CAPACITY.ROOT = previous
        self.assertTrue(any("approved H100 A3 Mega + H200 A3 Ultra" in item for item in errors))

    def test_live_contract_accepts_h200_a3_ultra(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_live_contract(root, "gke-h200-a3-ultragpu-8g")
            previous = CAPACITY.ROOT
            CAPACITY.ROOT = root
            try:
                _, profiles, errors = CAPACITY.live_contract()
            finally:
                CAPACITY.ROOT = previous
        self.assertEqual(profiles, CAPACITY.CANONICAL_POOL_PROFILES)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
