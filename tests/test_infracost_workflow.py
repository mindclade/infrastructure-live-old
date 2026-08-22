#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Behavioral tests for the Infracost merge-queue reporting contract."""

from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PULL_REQUEST_BASE = "1" * 40
MERGE_GROUP_BASE = "2" * 40


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RESOLVER = load("resolve_infracost_base", "scripts/resolve_infracost_base.py")
VALIDATOR = load(
    "validate_infracost_workflow", "scripts/validate_infracost_workflow.py"
)


class InfracostBaselineTest(unittest.TestCase):
    def test_pull_request_uses_payload_base_sha(self) -> None:
        payload = {"pull_request": {"base": {"sha": PULL_REQUEST_BASE}}}
        self.assertEqual(
            RESOLVER.resolve_base_sha("pull_request", payload), PULL_REQUEST_BASE
        )

    def test_merge_group_uses_payload_base_sha(self) -> None:
        payload = {"merge_group": {"base_sha": MERGE_GROUP_BASE}}
        self.assertEqual(
            RESOLVER.resolve_base_sha("merge_group", payload), MERGE_GROUP_BASE
        )

    def test_missing_or_symbolic_sha_fails_closed(self) -> None:
        for payload in (
            {"pull_request": {"base": {}}},
            {"pull_request": {"base": {"sha": "main"}}},
            {"merge_group": {"base_sha": "HEAD~1"}},
        ):
            event = "merge_group" if "merge_group" in payload else "pull_request"
            with self.subTest(event=event, payload=payload):
                with self.assertRaises(RESOLVER.BaselineResolutionError):
                    RESOLVER.resolve_base_sha(event, payload)

    def test_unsupported_event_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            RESOLVER.BaselineResolutionError, "unsupported event"
        ):
            RESOLVER.resolve_base_sha("push", {})


class InfracostWorkflowContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = VALIDATOR.load_workflow()

    def test_repository_workflow_satisfies_contract(self) -> None:
        self.assertEqual(VALIDATOR.validate_workflow(self.workflow), [])

    def test_merge_group_trigger_is_required(self) -> None:
        candidate = copy.deepcopy(self.workflow)
        del candidate["on"]["merge_group"]
        errors = VALIDATOR.validate_workflow(candidate)
        self.assertTrue(any("events must be exactly" in error for error in errors))

    def test_empty_baseline_fallback_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.workflow)
        baseline = next(
            step
            for step in candidate["jobs"]["infracost"]["steps"]
            if step.get("name") == "Calculate exact baseline"
        )
        baseline["run"] += '\necho \'{"projects":[]}\' > /tmp/base.json\n'
        errors = VALIDATOR.validate_workflow(candidate)
        self.assertTrue(any("successful empty baseline" in error for error in errors))

    def test_merge_group_commenting_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.workflow)
        candidate["jobs"]["comment"]["if"] = "${{ always() }}"
        errors = VALIDATOR.validate_workflow(candidate)
        self.assertTrue(any("successful pull-request" in error for error in errors))

    def test_comment_shell_interpolation_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.workflow)
        publish = next(
            step
            for step in candidate["jobs"]["comment"]["steps"]
            if step.get("name") == "Publish cost comment"
        )
        publish["run"] += '\necho "${{ github.repository }}"\n'
        errors = VALIDATOR.validate_workflow(candidate)
        self.assertTrue(any("must not interpolate" in error for error in errors))

    def test_non_reporting_or_permissive_verdict_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.workflow)
        candidate["jobs"]["verdict"]["name"] = "verdict"
        candidate["jobs"]["verdict"]["if"] = "${{ success() }}"
        candidate["jobs"]["verdict"]["permissions"] = {"contents": "read"}
        errors = VALIDATOR.validate_workflow(candidate)
        for expected in (
            "stable infracost / verdict",
            "report even when",
            "no repository or token permissions",
        ):
            self.assertTrue(any(expected in error for error in errors))

    def test_continue_on_error_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.workflow)
        candidate["jobs"]["infracost"]["continue-on-error"] = "true"
        candidate["jobs"]["verdict"]["steps"][0]["continue-on-error"] = "true"
        errors = VALIDATOR.validate_workflow(candidate)
        self.assertTrue(any("estimator must not override" in error for error in errors))
        self.assertTrue(any("verdict steps must not continue" in error for error in errors))

    def test_duplicate_yaml_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "workflow.yml"
            workflow.write_text("name: cost\nname: shadowed\n", encoding="utf-8")
            with self.assertRaisesRegex(
                VALIDATOR.WorkflowContractError, "duplicate workflow key"
            ):
                VALIDATOR.load_workflow(workflow)


if __name__ == "__main__":
    unittest.main()
