# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""account.hcl must parse for the credential-free `validate` job.

`plan.yml` maps every ring-0 identifier from a repository variable, so a variable that has not
been exported yet still reaches terragrunt — as the empty string, not as an absent name. That
distinction matters: `get_env(NAME, default)` returns its default only when the name is absent,
so a bare `jsondecode(get_env(NAME))` aborts HCL evaluation with `EOF` and takes every unit's
`terragrunt hcl validate` down with it, regardless of what the pull request changed.

Guarding the decode is not a relaxation. `1-org/automation-iam` types and validates both values,
so an empty decode is rejected there and plan/apply still fail closed.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_HCL = ROOT / "account.hcl"
PLAN_WORKFLOW = ROOT / ".github/workflows/plan.yml"

JSONDECODE_LINE = re.compile(r"^\s*(?P<name>\w+)\s*=\s*jsondecode\((?P<expr>.+)\)\s*$")
ENV_NAME = re.compile(r'get_env\(\s*"(?P<var>[A-Z0-9_]+)"')


def jsondecode_locals() -> list[tuple[str, str]]:
    """Return (local name, right-hand expression) for each jsondecode local in account.hcl."""
    found = []
    for line in ACCOUNT_HCL.read_text().splitlines():
        match = JSONDECODE_LINE.match(line)
        if match:
            found.append((match.group("name"), match.group("expr")))
    return found


class AccountContractTest(unittest.TestCase):
    def test_account_hcl_has_jsondecode_locals(self) -> None:
        """Guard the guard: a rename must not silently empty out the checks below."""
        self.assertTrue(
            jsondecode_locals(),
            "expected account.hcl to decode at least one JSON contract variable",
        )

    def test_jsondecode_locals_tolerate_an_exported_but_empty_variable(self) -> None:
        for name, expr in jsondecode_locals():
            with self.subTest(local=name):
                self.assertIn(
                    "coalesce(",
                    expr,
                    f"{name} must coalesce an empty variable to a parseable literal so the "
                    f"credential-free `validate` job can evaluate account.hcl; a bare "
                    f"jsondecode(get_env(...)) fails with EOF once plan.yml exports the name "
                    f"with an empty value",
                )

    def test_jsondecode_variables_are_exported_by_the_plan_workflow(self) -> None:
        """The empty-string case is only reachable because plan.yml maps these names."""
        workflow = PLAN_WORKFLOW.read_text()
        for name, expr in jsondecode_locals():
            for var in ENV_NAME.findall(expr):
                with self.subTest(local=name, variable=var):
                    self.assertIn(
                        f"{var}: ${{{{ vars.{var} }}}}",
                        workflow,
                        f"{var} is decoded by account.hcl but plan.yml does not map it from a "
                        f"repository variable",
                    )


if __name__ == "__main__":
    unittest.main()
