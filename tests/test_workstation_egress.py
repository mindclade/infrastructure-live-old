# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Tests for the fail-closed immutable-workstation qualification contract."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load("validate_workstation_egress", "scripts/validate_workstation_egress.py")
SELECT = load("select_apply_scopes_workstation", "scripts/select-apply-scopes.py")
SCOPE = load("terragrunt_scope_workstation", "scripts/terragrunt-scope.py")
CONTRACT = json.loads((ROOT / "contracts/workstation-egress.json").read_text())
SCHEMA = json.loads((ROOT / "contracts/workstation-egress.schema.json").read_text())

UNIT = "5-workloads/development/workstation"

FIREWALL_TEMPLATE = """locals {{
  rules = {{
    allow-egress-intra-vpc = {{
      direction          = "EGRESS"
      priority           = 1100
      action             = "allow"
      destination_ranges = ["10.0.0.0/8"]
    }}

    allow-egress-google-apis = {{
      direction          = "EGRESS"
      priority           = 1200
      action             = "allow"
      destination_ranges = ["199.36.153.4/30", "34.126.0.0/18"]
    }}
{extra}
    deny-egress-default = {{
      direction          = "EGRESS"
      priority           = {priority}
      action             = "deny"
      destination_ranges = [{deny}]
    }}
  }}
}}
"""

WORKSTATION_UNIT = """# ACTIVATION IS BLOCKED. See contracts/workstation-egress.json.
dependency "image" {
  config_path = "../workstation-image"
}
locals { module_version = "v0.4.0" }
inputs = {
  create_iap_ssh_firewall_rule = false
  image = dependency.image.outputs.image.self_link
  image_contract_sha256 = dependency.image.outputs.source_contract.image_contract_sha256
}
"""


def materialize(
    root: Path,
    *,
    extra_rule: str = "",
    deny: str = '"0.0.0.0/0"',
    priority: int = 65000,
    unit_text: str = WORKSTATION_UNIT,
) -> None:
    for relative in VALIDATOR.REQUIRED_SOURCE_PATHS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    artifact_inputs = (
        "WORKSTATION_IMAGE_SOURCE_STATE",
        "WORKSTATION_IMAGE_SOURCE_URI",
        "WORKSTATION_IMAGE_SOURCE_OBJECT_GENERATION",
        "WORKSTATION_IMAGE_SOURCE_SHA256",
        "WORKSTATION_IMAGE_CONTRACT_SHA256",
    )
    root.joinpath("account.hcl").write_text(
        "\n".join(f'get_env("{name}", "")' for name in artifact_inputs),
        encoding="utf-8",
    )
    workflow_contract = "\n".join(
        f"{name}: ${{{{ vars.{name} }}}}" for name in artifact_inputs
    )
    for workflow in ("apply.yml", "cost.yml", "drift.yml", "plan.yml"):
        root.joinpath(".github/workflows", workflow).write_text(
            workflow_contract, encoding="utf-8"
        )
    for environment in ("development", "production", "staging"):
        root.joinpath(
            f"3-networks/{environment}/firewall-baseline/terragrunt.hcl"
        ).write_text(
            FIREWALL_TEMPLATE.format(extra=extra_rule, deny=deny, priority=priority),
            encoding="utf-8",
        )
    root.joinpath(f"{UNIT}/terragrunt.hcl").write_text(unit_text, encoding="utf-8")


class WorkstationEgressTest(unittest.TestCase):
    def test_live_unit_is_development_scoped(self) -> None:
        self.assertEqual(
            SELECT.scope_for_path(f"{UNIT}/terragrunt.hcl"), {"development"}
        )
        self.assertEqual(
            SCOPE.validate_unit("development", UNIT, SCOPE.SCOPES["development"]), UNIT
        )
        with self.assertRaisesRegex(ValueError, "outside scope foundation"):
            SCOPE.validate_unit("foundation", UNIT, SCOPE.SCOPES["foundation"])

    def test_checked_in_contract_is_qualifying_and_fail_closed(self) -> None:
        self.assertEqual(VALIDATOR.validate(CONTRACT, SCHEMA), [])
        self.assertEqual(CONTRACT["status"], "qualifying")
        self.assertFalse(CONTRACT["workstation"]["activated"])
        self.assertTrue(CONTRACT["workstation"]["source_provisioning_complete"])
        self.assertTrue(CONTRACT["selected_design"]["implemented"])
        self.assertFalse(CONTRACT["selected_design"]["adds_egress_destination"])
        self.assertTrue(CONTRACT["evidence"]["runtime_fetches_absent"])
        self.assertFalse(CONTRACT["evidence"]["first_boot_qualified"])

    def test_source_evidence_cannot_regress(self) -> None:
        candidate = copy.deepcopy(CONTRACT)
        candidate["evidence"]["runtime_fetches_absent"] = False
        errors = VALIDATOR.policy_errors(candidate)
        self.assertTrue(
            any("restore runtime fetches" in error for error in errors), errors
        )

    def test_activated_contract_requires_every_evidence_gate(self) -> None:
        candidate = self._activated_contract()
        self.assertEqual(VALIDATOR.schema_errors(candidate, SCHEMA), [])
        candidate["evidence"]["vpc_sc_enforced_path_qualified"] = False
        errors = VALIDATOR.policy_errors(candidate)
        self.assertTrue(
            any("requires every evidence gate" in error for error in errors), errors
        )

    def test_selected_design_may_never_add_an_egress_destination(self) -> None:
        candidate = copy.deepcopy(CONTRACT)
        candidate["selected_design"]["adds_egress_destination"] = True
        self.assertIn(
            "[WSEGRESS-POLICY] the selected design may not add an egress destination",
            VALIDATOR.policy_errors(candidate),
        )

    def test_reviewed_destinations_may_not_open_the_internet(self) -> None:
        candidate = copy.deepcopy(CONTRACT)
        candidate["egress_baseline"]["reviewed_destinations"] = ["0.0.0.0/0"]
        self.assertIn(
            "[WSEGRESS-POLICY] 0.0.0.0/0 is never a reviewed egress destination",
            VALIDATOR.policy_errors(candidate),
        )

    def test_reviewed_destinations_may_not_be_broader_than_a_slash_eight(self) -> None:
        candidate = copy.deepcopy(CONTRACT)
        candidate["egress_baseline"]["reviewed_destinations"] = ["151.101.0.0/4"]
        errors = VALIDATOR.policy_errors(candidate)
        self.assertTrue(any("broader than /8" in error for error in errors), errors)

    def test_blocker_and_rejected_design_sets_are_exact(self) -> None:
        candidate = copy.deepcopy(CONTRACT)
        candidate["blockers"] = candidate["blockers"][:1]
        candidate["rejected_designs"] = candidate["rejected_designs"][:1]
        errors = VALIDATOR.policy_errors(candidate)
        self.assertIn(
            "[WSEGRESS-POLICY] qualifying lifecycle must retain the exact unresolved blocker set",
            errors,
        )
        self.assertIn(
            "[WSEGRESS-POLICY] the reviewed set of rejected designs may not be edited away",
            errors,
        )

    def test_intact_baseline_produces_no_firewall_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(root)
            self.assertEqual(VALIDATOR.firewall_errors(CONTRACT, root), [])
            self.assertEqual(VALIDATOR.network_sweep_errors(root), [])
            self.assertEqual(VALIDATOR.source_errors(CONTRACT, root), [])

    def test_weakened_default_deny_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(root, deny='"10.0.0.0/8"')
            errors = VALIDATOR.firewall_errors(CONTRACT, root)
        self.assertTrue(
            any("default egress deny no longer denies" in error for error in errors),
            errors,
        )

    def test_renumbered_default_deny_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(root, priority=100)
            errors = VALIDATOR.firewall_errors(CONTRACT, root)
        self.assertTrue(
            any("default egress deny no longer denies" in error for error in errors),
            errors,
        )

    def test_unreviewed_egress_destination_is_rejected(self) -> None:
        # The shape the workstation invites: a "narrow" rule above the deny that is really a
        # shared CDN block. The deny is untouched, so only this check sees it.
        extra = """
    allow-egress-package-cdn = {
      direction          = "EGRESS"
      priority           = 1300
      action             = "allow"
      destination_ranges = ["151.101.0.0/16"]
    }
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(root, extra_rule=extra)
            errors = VALIDATOR.firewall_errors(CONTRACT, root)
            self.assertEqual(VALIDATOR.network_sweep_errors(root), [])
        self.assertTrue(
            any("names an unreviewed destination: 151.101.0.0/16" in e for e in errors),
            errors,
        )

    def test_internet_egress_allow_is_rejected(self) -> None:
        extra = """
    allow-egress-internet = {
      direction          = "EGRESS"
      priority           = 1300
      action             = "allow"
      destination_ranges = ["0.0.0.0/0"]
    }
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(root, extra_rule=extra)
            sweep = VALIDATOR.network_sweep_errors(root)
            firewall = VALIDATOR.firewall_errors(CONTRACT, root)
        self.assertTrue(
            any("allows egress to the whole internet" in error for error in sweep), sweep
        )
        self.assertTrue(
            any("names an unreviewed destination: 0.0.0.0/0" in e for e in firewall),
            firewall,
        )

    def test_unit_must_keep_its_blocked_notice_until_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(
                root,
                unit_text=(
                    "# See contracts/workstation-egress.json.\n"
                    "inputs = {\n  create_iap_ssh_firewall_rule = false\n}\n"
                ),
            )
            errors = VALIDATOR.source_errors(CONTRACT, root)
        self.assertTrue(
            any("activation is blocked" in error for error in errors), errors
        )

    def test_unit_may_not_smuggle_a_startup_script(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(
                root,
                unit_text=(
                    WORKSTATION_UNIT.rstrip()
                    + '\nmetadata = { "startup-script" = "true" }\n'
                ),
            )
            errors = VALIDATOR.source_errors(CONTRACT, root)
        self.assertTrue(
            any("startup-script override" in error for error in errors), errors
        )

    def test_activated_contract_contradicts_a_blocked_unit(self) -> None:
        candidate = self._activated_contract()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(root)
            errors = VALIDATOR.source_errors(candidate, root)
        self.assertTrue(any("contradicts the unit" in error for error in errors), errors)

    @staticmethod
    def _activated_contract() -> dict:
        candidate = copy.deepcopy(CONTRACT)
        candidate["status"] = "activated"
        candidate["blockers"] = []
        for key in candidate["evidence"]:
            candidate["evidence"][key] = True
        candidate["workstation"]["activated"] = True
        return candidate


if __name__ == "__main__":
    unittest.main()
