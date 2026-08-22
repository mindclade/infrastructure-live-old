#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Semantically validate the fail-closed Infracost workflow contract."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/cost.yml"
ESTIMATOR_CONDITION = (
    "${{ github.event_name == 'merge_group' || "
    "github.event.pull_request.head.repo.full_name == github.repository }}"
)
COMMENT_CONDITION = (
    "${{ always() && github.event_name == 'pull_request' && "
    "needs.infracost.result == 'success' }}"
)


class WorkflowContractError(ValueError):
    """Raised when the workflow document itself is not safely parseable."""


class UniqueKeyLoader(yaml.BaseLoader):
    """Load YAML scalars as strings and reject ambiguous duplicate keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[str, Any]:
    if not isinstance(node, MappingNode):
        raise WorkflowContractError("expected a YAML mapping")
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise WorkflowContractError("workflow mapping keys must be strings")
        if key in result:
            raise WorkflowContractError(f"duplicate workflow key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def load_workflow(path: Path = WORKFLOW) -> dict[str, Any]:
    try:
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, yaml.YAMLError, WorkflowContractError) as exc:
        raise WorkflowContractError(f"unable to parse {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise WorkflowContractError(f"{path} must contain one workflow mapping")
    return document


def _mapping(
    value: object, field: str, errors: list[str]
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{field} must be a mapping")
        return {}
    return value


def _steps(job: Mapping[str, Any], field: str, errors: list[str]) -> list[Mapping[str, Any]]:
    value = job.get("steps")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        errors.append(f"{field}.steps must be a sequence")
        return []
    steps: list[Mapping[str, Any]] = []
    for index, step in enumerate(value):
        if not isinstance(step, Mapping):
            errors.append(f"{field}.steps[{index}] must be a mapping")
            continue
        steps.append(step)
    return steps


def _named_step(
    steps: Sequence[Mapping[str, Any]], name: str, errors: list[str]
) -> Mapping[str, Any]:
    matches = [step for step in steps if step.get("name") == name]
    if len(matches) != 1:
        errors.append(f"expected exactly one step named {name!r}; found {len(matches)}")
        return {}
    return matches[0]


def _needs(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {item for item in value if isinstance(item, str)}
    return set()


def _expression(value: object) -> str:
    return " ".join(str(value).split())


def validate_workflow(document: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    events = _mapping(document.get("on"), "on", errors)
    if set(events) != {"pull_request", "merge_group"}:
        errors.append("cost workflow events must be exactly pull_request and merge_group")
    if document.get("permissions") != {"contents": "read"}:
        errors.append("top-level permissions must be exactly contents: read")

    jobs = _mapping(document.get("jobs"), "jobs", errors)
    estimator = _mapping(jobs.get("infracost"), "jobs.infracost", errors)
    if _expression(estimator.get("if")) != ESTIMATOR_CONDITION:
        errors.append("estimator must run for merge groups and internal pull requests only")
    if estimator.get("environment") != "plan":
        errors.append("estimator must retain the protected plan environment")
    if estimator.get("permissions") != {"contents": "read", "id-token": "write"}:
        errors.append("estimator permissions must be exactly contents: read and id-token: write")
    if estimator.get("continue-on-error") is not None:
        errors.append("estimator must not override fail-closed job failure behavior")

    estimator_steps = _steps(estimator, "jobs.infracost", errors)
    if any(step.get("continue-on-error") is not None for step in estimator_steps):
        errors.append("estimator steps must not continue after a cost failure")
    checkout_steps = [step for step in estimator_steps if "actions/checkout@" in str(step.get("uses", ""))]
    if len(checkout_steps) != 1:
        errors.append(f"estimator must contain one checkout step; found {len(checkout_steps)}")
    else:
        checkout_with = _mapping(checkout_steps[0].get("with"), "checkout.with", errors)
        if checkout_with.get("fetch-depth") != "0":
            errors.append("estimator checkout must fetch full history for exact baseline validation")
        if checkout_with.get("persist-credentials") != "false":
            errors.append("estimator checkout must not persist GitHub credentials")

    resolver = _named_step(estimator_steps, "Resolve exact event baseline", errors)
    resolver_run = str(resolver.get("run", ""))
    if resolver.get("id") != "baseline":
        errors.append("baseline resolver step id must be baseline")
    if "python3 scripts/resolve_infracost_base.py" not in resolver_run:
        errors.append("baseline resolver must consume the tested event-payload resolver")
    if 'git merge-base --is-ancestor "$baseline_sha" HEAD' not in resolver_run:
        errors.append("baseline resolver must verify that the event base is a candidate ancestor")
    if "${{ github.event" in resolver_run:
        errors.append("baseline resolver must not interpolate event data directly into shell")

    baseline = _named_step(estimator_steps, "Calculate exact baseline", errors)
    baseline_env = _mapping(baseline.get("env"), "baseline.env", errors)
    if baseline_env.get("BASE_SHA") != "${{ steps.baseline.outputs.sha }}":
        errors.append("baseline calculation must consume only the validated resolver output")
    baseline_run = str(baseline.get("run", ""))
    for required in (
        'git worktree add --detach "$baseline_directory" "$BASE_SHA"',
        "infracost breakdown",
        "--out-file=/tmp/base.json",
        "test -s /tmp/base.json",
        "jq . /tmp/base.json >/dev/null",
    ):
        if required not in baseline_run:
            errors.append(f"baseline calculation omits required behavior: {required}")
    if '{"projects":[]}' in baseline_run or "||" in baseline_run:
        errors.append("baseline calculation must not synthesize a successful empty baseline")

    diff_step = _named_step(estimator_steps, "Calculate cost diff", errors)
    diff_run = str(diff_step.get("run", ""))
    if "--compare-to=/tmp/base.json" not in diff_run or "jq . /tmp/diff.json" not in diff_run:
        errors.append("cost diff must consume and validate the exact baseline result")

    comment = _mapping(jobs.get("comment"), "jobs.comment", errors)
    if _needs(comment.get("needs")) != {"infracost"}:
        errors.append("comment job must depend only on the estimator")
    if _expression(comment.get("if")) != COMMENT_CONDITION:
        errors.append("comment job must run only for successful pull-request estimates")
    if comment.get("permissions") != {"contents": "read", "pull-requests": "write"}:
        errors.append("comment permissions must be exactly contents: read and pull-requests: write")
    comment_steps = _steps(comment, "jobs.comment", errors)
    publish = _named_step(comment_steps, "Publish cost comment", errors)
    publish_env = _mapping(publish.get("env"), "comment.publish.env", errors)
    expected_publish_env = {
        "INFRACOST_GITHUB_TOKEN": "${{ github.token }}",
        "INFRACOST_PULL_REQUEST": "${{ github.event.pull_request.number }}",
        "INFRACOST_REPOSITORY": "${{ github.repository }}",
    }
    if publish_env != expected_publish_env:
        errors.append("cost comment inputs must use the exact environment-variable boundary")
    publish_run = str(publish.get("run", ""))
    for expression in expected_publish_env.values():
        if expression in publish_run:
            errors.append("cost comment must not interpolate GitHub expressions into shell")
    for variable in expected_publish_env:
        if f"${{{variable}}}" not in publish_run:
            errors.append(f"cost comment must consume {variable} through the shell environment")

    verdict = _mapping(jobs.get("verdict"), "jobs.verdict", errors)
    if verdict.get("name") != "infracost / verdict":
        errors.append("verdict must expose the stable infracost / verdict context")
    if _needs(verdict.get("needs")) != {"infracost"}:
        errors.append("verdict must depend only on the estimator")
    if _expression(verdict.get("if")) != "${{ always() }}":
        errors.append("verdict must report even when the estimator fails or is skipped")
    if verdict.get("permissions") != {}:
        errors.append("verdict must have no repository or token permissions")
    if verdict.get("continue-on-error") is not None:
        errors.append("verdict must not override fail-closed job failure behavior")
    verdict_steps = _steps(verdict, "jobs.verdict", errors)
    if any(step.get("continue-on-error") is not None for step in verdict_steps):
        errors.append("verdict steps must not continue after a failed result check")
    verdict_step = _named_step(verdict_steps, "Require a successful cost estimate", errors)
    verdict_env = _mapping(verdict_step.get("env"), "verdict.env", errors)
    if verdict_env.get("INFRACOST_RESULT") != "${{ needs.infracost.result }}":
        errors.append("verdict must consume the estimator job result")
    verdict_run = str(verdict_step.get("run", ""))
    if '[[ "$INFRACOST_RESULT" != "success" ]]' not in verdict_run or "exit 1" not in verdict_run:
        errors.append("verdict must fail closed for every non-success estimator result")

    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=Path, default=WORKFLOW)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        document = load_workflow(args.workflow)
    except WorkflowContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    errors = validate_workflow(document)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Infracost workflow contract validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
