#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Validate module interfaces against one exact monorepo commit.

The existing candidate validator intentionally reads a worktree. This wrapper
materializes a detached local clone at an exact 40-character commit ID, then
runs that validator against the immutable snapshot. It performs no network or
source-repository mutation.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path


FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")
SEMVER = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")


class CandidateError(RuntimeError):
    """A release candidate is not an exact, locally available commit."""


def _run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def resolve_exact_commit(repo: Path, candidate_ref: str) -> str:
    if not FULL_COMMIT.fullmatch(candidate_ref):
        raise CandidateError("candidate ref must be a lowercase 40-character commit SHA")
    try:
        result = _run(
            ["git", "-C", str(repo), "rev-parse", "--verify", f"{candidate_ref}^{{commit}}"],
            capture=True,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip()
        raise CandidateError(f"candidate commit is not available locally: {detail}") from error
    resolved = result.stdout.strip()
    if resolved != candidate_ref:
        raise CandidateError(f"candidate ref resolved to unexpected commit {resolved}")
    return resolved


def validate_candidate(repo: Path, candidate_version: str, candidate_ref: str) -> None:
    if not repo.is_dir():
        raise CandidateError(f"monorepo does not exist: {repo}")
    if not SEMVER.fullmatch(candidate_version):
        raise CandidateError("candidate version must be an exact vMAJOR.MINOR.PATCH version")
    resolve_exact_commit(repo, candidate_ref)
    with tempfile.TemporaryDirectory(prefix="mindclade-module-candidate-") as temporary:
        snapshot = Path(temporary) / "monorepo"
        _run(
            [
                "git",
                "clone",
                "--quiet",
                "--no-hardlinks",
                "--no-checkout",
                str(repo),
                str(snapshot),
            ]
        )
        _run(["git", "-C", str(snapshot), "checkout", "--quiet", "--detach", candidate_ref])
        checked_out = _run(
            ["git", "-C", str(snapshot), "rev-parse", "HEAD"], capture=True
        ).stdout.strip()
        if checked_out != candidate_ref:
            raise CandidateError(f"detached snapshot resolved to unexpected commit {checked_out}")
        for validator_name in (
            "validate-module-interfaces.py",
            "validate-capacity-contract.py",
            "validate-workload-identity-contract.py",
        ):
            validator = Path(__file__).with_name(validator_name)
            _run(
                [
                    sys.executable,
                    str(validator),
                    "--monorepo",
                    str(snapshot),
                    "--candidate-version",
                    candidate_version,
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monorepo", type=Path, required=True)
    parser.add_argument("--candidate-version", required=True)
    parser.add_argument("--candidate-ref", required=True)
    args = parser.parse_args()
    try:
        validate_candidate(args.monorepo.resolve(), args.candidate_version, args.candidate_ref)
    except (CandidateError, subprocess.CalledProcessError) as error:
        print(f"release-candidate validation failed: {error}", file=sys.stderr)
        return 1
    print(
        f"module, capacity, and workload identity interfaces match {args.candidate_version} "
        f"at exact commit {args.candidate_ref}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
