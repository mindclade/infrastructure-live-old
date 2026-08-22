#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Resolve the immutable baseline commit from a supported GitHub event payload."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


COMMIT_SHA = re.compile(r"[0-9a-f]{40}")


class BaselineResolutionError(ValueError):
    """Raised when an event cannot yield one exact baseline commit."""


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BaselineResolutionError(f"event field {field!r} must be an object")
    return value


def resolve_base_sha(event_name: str, payload: Mapping[str, Any]) -> str:
    """Return the exact base SHA for a pull request or merge-group event."""
    if event_name == "pull_request":
        pull_request = _mapping(payload.get("pull_request"), "pull_request")
        base = _mapping(pull_request.get("base"), "pull_request.base")
        sha = base.get("sha")
        field = "pull_request.base.sha"
    elif event_name == "merge_group":
        merge_group = _mapping(payload.get("merge_group"), "merge_group")
        sha = merge_group.get("base_sha")
        field = "merge_group.base_sha"
    else:
        raise BaselineResolutionError(
            f"unsupported event {event_name!r}; expected pull_request or merge_group"
        )

    if not isinstance(sha, str) or COMMIT_SHA.fullmatch(sha) is None:
        raise BaselineResolutionError(
            f"event field {field!r} must be one lowercase 40-character commit SHA"
        )
    return sha


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    parser.add_argument(
        "--event-name",
        default=os.environ.get("GITHUB_EVENT_NAME", ""),
        help="GitHub event name (defaults to GITHUB_EVENT_NAME)",
    )
    parser.add_argument(
        "--event-path",
        type=Path,
        default=Path(event_path) if event_path else None,
        help="GitHub event JSON path (defaults to GITHUB_EVENT_PATH)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.event_name:
        print("error: GITHUB_EVENT_NAME is required", file=sys.stderr)
        return 2
    if args.event_path is None:
        print("error: GITHUB_EVENT_PATH is required", file=sys.stderr)
        return 2
    try:
        payload = json.loads(args.event_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise BaselineResolutionError("event payload must be a JSON object")
        sha = resolve_base_sha(args.event_name, payload)
    except (BaselineResolutionError, json.JSONDecodeError, OSError) as exc:
        print(f"error: unable to resolve Infracost baseline: {exc}", file=sys.stderr)
        return 2
    print(sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
