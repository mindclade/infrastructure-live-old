#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Classify a GCS state-prefix listing without confusing errors with emptiness."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


NO_OBJECTS = "ERROR: (gcloud.storage.ls) One or more URLs matched no objects."


def classify(status: int, stderr: str) -> str:
    normalized = stderr[:-1] if stderr.endswith("\n") else stderr
    if status == 0:
        if normalized:
            raise ValueError("successful state-prefix listing wrote unexpected stderr")
        return "existing-or-empty"
    if status == 1 and normalized == NO_OBJECTS:
        return "fresh"
    raise ValueError(
        f"state-prefix listing failed with status {status}; refusing to classify it as empty"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", required=True, type=int)
    parser.add_argument("--stderr-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = classify(args.status, args.stderr_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
