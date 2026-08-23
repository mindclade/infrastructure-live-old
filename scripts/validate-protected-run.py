#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Fail closed when a protected plan/apply run is stale or changes source."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = 1
MAXIMUM_PLAN_AGE_SECONDS = 6 * 60 * 60
FUTURE_CLOCK_SKEW_SECONDS = 60
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
CHANGE_REFERENCE_PATTERN = re.compile(
    r"^(?:CHG|INC|SEC|DR)-[A-Za-z0-9][A-Za-z0-9._-]{2,127}$"
)
METADATA_KEYS = {
    "schema_version",
    "repository",
    "run_id",
    "event_sha",
    "target_sha",
    "default_head_sha",
    "mode",
    "created_at_epoch",
    "maximum_age_seconds",
}


class GuardError(ValueError):
    """The protected run does not satisfy its fail-closed contract."""


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized in ("", "false"):
        return False
    raise GuardError(f"invalid boolean value: {value!r}")


def require_sha(value: str, label: str) -> str:
    normalized = value.strip().lower()
    if SHA_PATTERN.fullmatch(normalized) is None:
        raise GuardError(f"{label} must be a full 40-character commit SHA")
    return normalized


def github_json(path: str) -> dict[str, Any]:
    token = os.environ.get("GH_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    if not token or not repository:
        raise GuardError("GH_TOKEN and GITHUB_REPOSITORY are required")
    request = urllib.request.Request(
        f"{api_url}/repos/{repository}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise GuardError(f"GitHub default-head lookup failed: {error}") from error
    if not isinstance(payload, dict):
        raise GuardError("GitHub returned a non-object response")
    return payload


def current_default_head() -> tuple[str, str]:
    repository = github_json("")
    default_branch = repository.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch:
        raise GuardError("GitHub repository response omits default_branch")
    encoded = urllib.parse.quote(default_branch, safe="")
    reference = github_json(f"/git/ref/heads/{encoded}")
    target = reference.get("object")
    sha = target.get("sha") if isinstance(target, dict) else None
    if not isinstance(sha, str):
        raise GuardError("GitHub default-branch reference omits its commit SHA")
    return default_branch, require_sha(sha, "current default head")


def git_is_ancestor(git_root: Path, older: str, newer: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=git_root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise GuardError(f"git ancestry check failed: {result.stderr.strip()}")


def resolve_source(
    *,
    event_name: str,
    event_ref: str,
    event_sha: str,
    default_branch: str,
    default_head_sha: str,
    source_rollback: bool,
    source_rollback_sha: str,
    change_reference: str,
    is_ancestor: Callable[[str, str], bool],
) -> tuple[str, str]:
    event_sha = require_sha(event_sha, "event SHA")
    default_head_sha = require_sha(default_head_sha, "default-head SHA")
    expected_ref = f"refs/heads/{default_branch}"
    if event_ref != expected_ref:
        raise GuardError(f"protected run must be dispatched from {expected_ref}")
    if event_sha != default_head_sha:
        raise GuardError("workflow source is not the current default-branch head")
    rollback_sha = source_rollback_sha.strip().lower()
    if not source_rollback:
        if rollback_sha:
            raise GuardError("source_rollback_sha requires source_rollback=true")
        return event_sha, "current"
    if event_name != "workflow_dispatch":
        raise GuardError("source rollback is allowed only by explicit workflow dispatch")
    target_sha = require_sha(rollback_sha, "source rollback SHA")
    if target_sha == default_head_sha:
        raise GuardError("source rollback SHA must be older than the current default head")
    if CHANGE_REFERENCE_PATTERN.fullmatch(change_reference.strip()) is None:
        raise GuardError("source rollback requires a CHG-, INC-, SEC-, or DR- reference")
    if not is_ancestor(target_sha, default_head_sha):
        raise GuardError("source rollback SHA must be a strict ancestor of the default head")
    return target_sha, "rollback"


def validate_metadata(
    payload: Any,
    *,
    repository: str,
    run_id: str,
    event_sha: str,
    expected_target_sha: str,
    expected_default_head_sha: str,
    expected_mode: str,
    now: int,
) -> None:
    if not isinstance(payload, dict) or set(payload) != METADATA_KEYS:
        raise GuardError("protected-run metadata has an unexpected schema")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise GuardError("protected-run metadata schema version is unsupported")
    expected_strings = {
        "repository": repository,
        "run_id": run_id,
        "event_sha": require_sha(event_sha, "event SHA"),
        "target_sha": require_sha(expected_target_sha, "expected target SHA"),
        "default_head_sha": require_sha(
            expected_default_head_sha, "expected default-head SHA"
        ),
        "mode": expected_mode,
    }
    for key, value in expected_strings.items():
        if payload.get(key) != value:
            raise GuardError(f"protected-run metadata {key} does not match this run")
    created = payload.get("created_at_epoch")
    maximum_age = payload.get("maximum_age_seconds")
    if type(created) is not int or maximum_age != MAXIMUM_PLAN_AGE_SECONDS:
        raise GuardError("protected-run metadata has an invalid plan-age contract")
    age = now - created
    if age < -FUTURE_CLOCK_SKEW_SECONDS:
        raise GuardError("protected plan creation time is in the future")
    if age > MAXIMUM_PLAN_AGE_SECONDS:
        raise GuardError("protected plan is older than the six-hour maximum")


def write_outputs(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--event-ref", required=True)
    parser.add_argument("--event-sha", required=True)
    parser.add_argument("--source-rollback", default="false")
    parser.add_argument("--source-rollback-sha", default="")
    parser.add_argument("--change-reference", default="")
    parser.add_argument("--git-root", type=Path, default=Path("."))


def resolve_from_arguments(args: argparse.Namespace) -> tuple[str, str, str]:
    default_branch, default_head_sha = current_default_head()
    target_sha, mode = resolve_source(
        event_name=args.event_name,
        event_ref=args.event_ref,
        event_sha=args.event_sha,
        default_branch=default_branch,
        default_head_sha=default_head_sha,
        source_rollback=parse_bool(args.source_rollback),
        source_rollback_sha=args.source_rollback_sha,
        change_reference=args.change_reference,
        is_ancestor=lambda older, newer: git_is_ancestor(args.git_root, older, newer),
    )
    return target_sha, default_head_sha, mode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("source")
    add_source_arguments(source)
    source.add_argument("--github-output", type=Path, required=True)
    check = commands.add_parser("check-source")
    add_source_arguments(check)
    check.add_argument("--expected-target-sha", required=True)
    check.add_argument("--expected-default-head-sha", required=True)
    check.add_argument("--expected-mode", choices=("current", "rollback"), required=True)
    record = commands.add_parser("record-plan")
    record.add_argument("--repository", required=True)
    record.add_argument("--run-id", required=True)
    record.add_argument("--event-sha", required=True)
    record.add_argument("--target-sha", required=True)
    record.add_argument("--default-head-sha", required=True)
    record.add_argument("--mode", choices=("current", "rollback"), required=True)
    record.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate-plan")
    add_source_arguments(validate)
    validate.add_argument("--metadata", type=Path, required=True)
    validate.add_argument("--repository", required=True)
    validate.add_argument("--run-id", required=True)
    validate.add_argument("--expected-target-sha", required=True)
    validate.add_argument("--expected-default-head-sha", required=True)
    validate.add_argument("--expected-mode", choices=("current", "rollback"), required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command in ("source", "check-source", "validate-plan"):
            target_sha, default_head_sha, mode = resolve_from_arguments(args)
            expected = getattr(args, "expected_target_sha", target_sha)
            expected_head = getattr(args, "expected_default_head_sha", default_head_sha)
            expected_mode = getattr(args, "expected_mode", mode)
            if (target_sha, default_head_sha, mode) != (
                require_sha(expected, "expected target SHA"),
                require_sha(expected_head, "expected default-head SHA"),
                expected_mode,
            ):
                raise GuardError("protected-run source changed after its initial guard")
            if args.command == "source":
                write_outputs(
                    args.github_output,
                    {
                        "target_sha": target_sha,
                        "default_head_sha": default_head_sha,
                        "mode": mode,
                    },
                )
            elif args.command == "validate-plan":
                payload = json.loads(args.metadata.read_text(encoding="utf-8"))
                validate_metadata(
                    payload,
                    repository=args.repository,
                    run_id=args.run_id,
                    event_sha=args.event_sha,
                    expected_target_sha=target_sha,
                    expected_default_head_sha=default_head_sha,
                    expected_mode=mode,
                    now=int(time.time()),
                )
        else:
            event_sha = require_sha(args.event_sha, "event SHA")
            target_sha = require_sha(args.target_sha, "target SHA")
            default_head_sha = require_sha(args.default_head_sha, "default-head SHA")
            payload = {
                "schema_version": SCHEMA_VERSION,
                "repository": args.repository,
                "run_id": args.run_id,
                "event_sha": event_sha,
                "target_sha": target_sha,
                "default_head_sha": default_head_sha,
                "mode": args.mode,
                "created_at_epoch": int(time.time()),
                "maximum_age_seconds": MAXIMUM_PLAN_AGE_SECONDS,
            }
            args.output.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        print(f"protected-run {args.command} guard passed")
        return 0
    except (GuardError, OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
