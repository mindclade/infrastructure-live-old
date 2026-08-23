#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Compare infrastructure and GitOps workstation-image qualification contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INFRASTRUCTURE_CONTRACT = ROOT / "contracts/workstation-egress.json"
GITOPS_CONTRACT = Path("qualification/workstation-image-readiness.yaml")

EXPECTED_AUTHORITY = {
    "sourceRepository": "mindclade/mindclade-internal-monorepo",
    "workflowRepository": "mindclade/.github",
    "infrastructureRepository": "mindclade/infrastructure-live",
    "gitopsRole": "evidence-only",
}
EXPECTED_SOURCE_GATES = {
    "imageContractValidated",
    "runtimeFetchesAbsent",
    "createOnlyPublicationContract",
    "terraformImageAuthoritySeparated",
    "governedSourceEvidenceTransition",
}
EXPECTED_ACTIVATION = {
    "argoReconciliationAllowed": False,
    "productActivationAllowed": False,
    "selected": False,
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one YAML object")
    return value


def validation_errors(
    infrastructure: dict[str, Any], gitops: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    spec = gitops.get("spec")
    if not isinstance(spec, dict):
        return ["GitOps workstation qualification spec must be an object"]

    if spec.get("authority") != EXPECTED_AUTHORITY:
        errors.append("GitOps workstation authority boundary differs from the reviewed handoff")
    if spec.get("releases") != infrastructure.get("releases"):
        errors.append("GitOps workstation releases differ from infrastructure")

    source = spec.get("sourceGates")
    evidence = infrastructure.get("evidence")
    if not isinstance(source, dict) or set(source) != EXPECTED_SOURCE_GATES:
        errors.append("GitOps workstation source gate set differs")
    elif not isinstance(evidence, dict):
        errors.append("infrastructure workstation evidence must be an object")
    else:
        expected_claims = {
            "imageContractValidated": evidence.get("image_contract_source_validated"),
            "runtimeFetchesAbsent": evidence.get("runtime_fetches_absent"),
            "createOnlyPublicationContract": True,
            "terraformImageAuthoritySeparated": True,
            "governedSourceEvidenceTransition": True,
        }
        if source != expected_claims:
            errors.append("GitOps workstation source claims differ from infrastructure")

    # The checked-in lifecycle is deliberately source-only. Advancing either repository alone
    # must fail this comparison and require a coordinated, evidence-backed transition.
    if infrastructure.get("status") != "qualifying" or spec.get("state") != "qualifying":
        errors.append("workstation qualification lifecycle differs before connected evidence")
    connected = spec.get("connectedGates")
    if not isinstance(connected, dict) or not connected or any(connected.values()):
        errors.append("GitOps workstation connected gates must remain false")
    if spec.get("activation") != EXPECTED_ACTIVATION:
        errors.append("GitOps may not reconcile, select, or activate the workstation")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gitops",
        type=Path,
        required=True,
        help="path to the paired GitOps checkout",
    )
    args = parser.parse_args()
    gitops_root = args.gitops.resolve()

    errors: list[str] = []
    if not (gitops_root / ".git").exists():
        errors.append(f"--gitops must be a Git checkout: {gitops_root}")
    try:
        infrastructure = load_json(INFRASTRUCTURE_CONTRACT)
        gitops = load_yaml(gitops_root / GITOPS_CONTRACT)
        errors.extend(validation_errors(infrastructure, gitops))
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
        errors.append(str(error))

    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("workstation image release and authority contract passed with GitOps parity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
