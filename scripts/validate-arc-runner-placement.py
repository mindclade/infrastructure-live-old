#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Validate both sides of the infrastructure/GitOps ARC placement handoff."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUNNER_UNIT = Path("5-workloads/ci/nodepools/runner/terragrunt.hcl")
SPOT_UNIT = Path("5-workloads/ci/nodepools/runner-spot/terragrunt.hcl")
RUNNER_RELEASES = ("canary", "build", "qualify", "presubmit")
EXPECTED_NODE_SELECTOR = {
    "iam.gke.io/gke-metadata-server-enabled": "true",
    "mindclade.dev/workload-class": "arc-runner",
}
EXPECTED_TOLERATIONS = [
    {
        "key": "scheduling.mindclade.dev/arc-runner",
        "operator": "Equal",
        "value": "true",
        "effect": "NoSchedule",
    }
]


def require_literal(text: str, pattern: str, message: str, errors: list[str]) -> None:
    if re.search(pattern, text, re.MULTILINE) is None:
        errors.append(message)


def validate_runner_unit_text(text: str) -> list[str]:
    errors: list[str] = []
    literals = (
        (
            r'^\s*module_version\s*=\s*"v0\.4\.0"\s*$',
            "ARC runner pool must select the planned v0.4.0 module contract",
        ),
        (
            r'^\s*service_account_id\s*=\s*"sa-arc-runner-nodes"\s*$',
            "ARC runner pool must use its dedicated node service account",
        ),
        (
            r'^\s*capacity_type\s*=\s*"ON_DEMAND"\s*$',
            "ARC runner pool must remain on-demand until Spot is qualified",
        ),
        (
            r"^\s*total_min_nodes\s*=\s*0\s*$",
            "ARC runner pool must retain its zero idle floor",
        ),
        (
            r"^\s*total_max_nodes\s*=\s*6\s*$",
            "ARC runner pool release-lane ceiling must remain six nodes",
        ),
        (
            r'^\s*key\s*=\s*"scheduling\.mindclade\.dev/arc-runner"\s*$',
            "ARC runner pool omits the dedicated scheduling taint",
        ),
        (
            r'^\s*value\s*=\s*"true"\s*$',
            "ARC runner pool taint omits its exact value",
        ),
        (
            r'^\s*effect\s*=\s*"NO_SCHEDULE"\s*$',
            "ARC runner pool taint must use NO_SCHEDULE",
        ),
        (
            r'^\s*"mindclade\.dev/workload-class"\s*=\s*"arc-runner"\s*$',
            "ARC runner pool omits the GitOps-selected node label",
        ),
    )
    for pattern, message in literals:
        require_literal(text, pattern, message, errors)
    for dependency in (
        'config_path = "../../arc-gke"',
        'config_path = "../../../../1-org/common-projects"',
        'config_path = "../../../../3-networks/ci/arc-vpc"',
    ):
        if dependency not in text:
            errors.append(f"ARC runner pool omits dependency: {dependency}")
    return errors


def validate_spot_unit_text(text: str) -> list[str]:
    errors: list[str] = []
    for pattern, message in (
        (r'^\s*module_version\s*=\s*"v0\.4\.0"\s*$', "ARC Spot pool must select v0.4.0"),
        (r'^\s*service_account_id\s*=\s*"sa-arc-presubmit-spot-nodes"\s*$', "ARC Spot pool must use its dedicated identity"),
        (r'^\s*capacity_type\s*=\s*"SPOT"\s*$', "ARC presubmit pool must remain Spot"),
        (r'^\s*spot_approval\s*=\s*"I ACCEPT EVICTION AND CAPACITY-LOSS RISK"\s*$', "ARC Spot risk acknowledgement differs"),
        (r"^\s*total_min_nodes\s*=\s*0\s*$", "ARC Spot pool must retain a zero floor"),
        (r"^\s*total_max_nodes\s*=\s*8\s*$", "ARC Spot pool ceiling must remain eight nodes"),
        (r'^\s*key\s*=\s*"scheduling\.mindclade\.dev/arc-presubmit"\s*$', "ARC Spot pool omits the presubmit taint"),
        (r'^\s*"mindclade\.dev/workload-class"\s*=\s*"arc-presubmit-spot"\s*$', "ARC Spot pool is not isolated from active runner scale sets"),
    ):
        require_literal(text, pattern, message, errors)
    for dependency in (
        'config_path = "../../arc-gke"',
        'config_path = "../../../../1-org/common-projects"',
        'config_path = "../../../../3-networks/ci/arc-vpc"',
    ):
        if dependency not in text:
            errors.append(f"ARC Spot pool omits dependency: {dependency}")
    return errors


def validate_infrastructure(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    required = (
        RUNNER_UNIT,
        Path("5-workloads/ci/nodepools/runner/.terraform.lock.hcl"),
        SPOT_UNIT,
        Path("5-workloads/ci/nodepools/runner-spot/.terraform.lock.hcl"),
        Path("5-workloads/ci/README.md"),
    )
    for relative in required:
        if not (root / relative).is_file():
            errors.append(f"missing ARC runner placement source: {relative}")
    unit = root / RUNNER_UNIT
    if unit.is_file():
        errors.extend(validate_runner_unit_text(unit.read_text(encoding="utf-8")))
    spot_unit = root / SPOT_UNIT
    if spot_unit.is_file():
        errors.extend(validate_spot_unit_text(spot_unit.read_text(encoding="utf-8")))
    readme = root / "5-workloads/ci/README.md"
    if readme.is_file():
        documentation = readme.read_text(encoding="utf-8")
        for required_text in (
            "planned `v0.4.0`",
            "5-workloads/ci/nodepools/runner",
            "mindclade.dev/workload-class=arc-runner",
            "scheduling.mindclade.dev/arc-runner=true:NoSchedule",
            "Apply the infrastructure runner pool before reconciling",
            "5-workloads/ci/nodepools/runner-spot",
            "mindclade.dev/workload-class=arc-presubmit-spot",
        ):
            if required_text not in documentation:
                errors.append(f"ARC cloud-foundation documentation omits: {required_text}")
        for stale in ("planned `v0.2.0`", "164f2998f9540243a0df769dc78c96677134c70a"):
            if stale in documentation:
                errors.append(f"ARC cloud-foundation documentation retains stale ref: {stale}")
    return errors


def load_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one YAML object")
    return payload


def validate_gitops(gitops: Path) -> list[str]:
    errors: list[str] = []
    for release in RUNNER_RELEASES:
        for tree in ("values", "rendered"):
            path = gitops / f"arc/{tree}/{release}.yaml"
            try:
                if tree == "values":
                    payload = load_mapping(path)
                    template = payload.get("template")
                    spec = template.get("spec") if isinstance(template, dict) else None
                else:
                    documents = [
                        document
                        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
                        if isinstance(document, dict)
                        and document.get("kind") == "AutoscalingRunnerSet"
                    ]
                    if len(documents) != 1:
                        errors.append(
                            f"{path} must contain exactly one AutoscalingRunnerSet"
                        )
                        continue
                    rendered_spec = documents[0].get("spec")
                    template = (
                        rendered_spec.get("template")
                        if isinstance(rendered_spec, dict)
                        else None
                    )
                    spec = template.get("spec") if isinstance(template, dict) else None
                if not isinstance(spec, dict):
                    errors.append(f"{path} omits the runner pod spec")
                    continue
                if spec.get("nodeSelector") != EXPECTED_NODE_SELECTOR:
                    errors.append(f"{path} disagrees with the infrastructure node label")
                if spec.get("tolerations") != EXPECTED_TOLERATIONS:
                    errors.append(f"{path} disagrees with the infrastructure node taint")
            except (OSError, ValueError, yaml.YAMLError) as error:
                errors.append(str(error))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gitops",
        type=Path,
        help="also validate the paired GitOps values and rendered manifests",
    )
    args = parser.parse_args()

    errors = validate_infrastructure()
    if args.gitops is not None:
        gitops = args.gitops.resolve()
        if not (gitops / ".git").exists():
            errors.append(f"--gitops must be a Git checkout: {gitops}")
        else:
            errors.extend(validate_gitops(gitops))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    suffix = " with GitOps parity" if args.gitops is not None else ""
    print(f"ARC runner placement contract passed{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
