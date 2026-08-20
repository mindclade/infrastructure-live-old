#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# MINDCLADE CONFIDENTIAL - PROPRIETARY AND TRADE SECRET
# Copyright (c) 2026 Mindclade. All rights reserved.
"""Validate the Mindclade production repository contract.

This check intentionally uses only the Python standard library.
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPOSITORY='infrastructure-live'
CONTRACT=json.loads('{"authority": ["normal-gcp-organization-infrastructure", "folders", "org-policy", "environments", "networks", "projects", "gke", "managed-cloud-services"], "forbidden_authority": ["ring0-state-foundation", "argocd-installation", "kubernetes-desired-state", "application-source"], "forbidden_paths": [".terraform", ".terragrunt-cache", "5-workloads/development/argocd", "5-workloads/staging/argocd", "5-workloads/production/argocd"], "repository_class": "production-control", "required_paths": ["1-org", "2-environments/development", "2-environments/staging", "2-environments/production", "3-networks", "4-projects", "5-workloads/development", "5-workloads/staging", "5-workloads/production", "root.hcl"], "visibility": "private"}')
ERRORS=[]

def error(msg): ERRORS.append(msg)

def repository_paths() -> list[Path]:
    """Return version-controlled paths in a checkout, or all paths in an exported tree."""
    if (ROOT / ".git").exists():
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
        return [ROOT / raw.decode("utf-8", errors="surrogateescape") for raw in result.stdout.split(b"\0") if raw]
    return list(ROOT.rglob("*"))

TRACKED_PATHS = repository_paths()
TRACKED_RELATIVE = {p.relative_to(ROOT).as_posix() for p in TRACKED_PATHS}

def tracked_prefix_exists(relative: str) -> bool:
    prefix = relative.rstrip("/")
    return prefix in TRACKED_RELATIVE or any(path.startswith(prefix + "/") for path in TRACKED_RELATIVE)

for rel in CONTRACT["required_paths"]:
    if not (ROOT/rel).exists(): error(f"missing required path: {rel}")
for rel in CONTRACT["forbidden_paths"]:
    if tracked_prefix_exists(rel): error(f"forbidden tracked path present: {rel}")
for p in TRACKED_PATHS:
    relative = p.relative_to(ROOT)
    if any(part in {".terraform",".terragrunt-cache","__MACOSX","__pycache__"} for part in relative.parts):
        error(f"local/cache artifact is tracked: {relative}")
    if p.name.startswith("._") or ".tfstate" in p.name or p.suffix in {".pyc",".tfplan"}:
        error(f"generated/sensitive artifact is tracked: {relative}")
    if p.is_symlink(): error(f"symlink forbidden in delivery: {relative}")

# GitHub Actions must be immutable and least privilege.
for p in (ROOT/".github/workflows").glob("*.y*ml") if (ROOT/".github/workflows").exists() else []:
    text=p.read_text("utf-8",errors="ignore")
    for use in re.findall(r"(?m)^\s*-?\s*uses:\s*([^#\s]+)",text):
        if use.startswith("./"): continue
        if not (re.search(r"@[0-9a-f]{40}$",use) or re.search(r"@sha256:[0-9a-f]{64}$",use) or re.fullmatch(r"Mindclade/\.github/\.github/workflows/[^@]+@v[0-9]+\.[0-9]+\.[0-9]+",use)):
            error(f"workflow action is not immutable-pinned in {p.relative_to(ROOT)}: {use}")
    if "permissions:" not in text:
        error(f"workflow lacks explicit permissions: {p.relative_to(ROOT)}")

# No obvious plaintext credentials. Values are intentionally conservative.
secret_patterns=[
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
]
for p in TRACKED_PATHS:
    if not p.is_file() or p.stat().st_size>2_000_000: continue
    try:text=p.read_text("utf-8",errors="ignore")
    except:continue
    for pattern in secret_patterns:
        if pattern.search(text): error(f"possible credential in {p.relative_to(ROOT)}")

if REPOSITORY=="bootstrap":
    for forbidden in ("modules/folders","modules/governance"):
        if (ROOT/forbidden).exists(): error(f"Ring-0 boundary violation: {forbidden}")
    combined="\n".join(p.read_text("utf-8",errors="ignore") for p in ROOT.rglob("*.tf"))
    if re.search(r'module\s+"(?:folders|governance)"',combined): error("Ring-0 root still instantiates folders/governance")
elif REPOSITORY=="github-config":
    text=(ROOT/"catalog/repositories.yaml").read_text("utf-8",errors="ignore")
    for repo in (".github","bootstrap","github-config","infrastructure-live","gitops","mindclade-internal-monorepo"):
        if repo not in text:error(f"repository catalog missing {repo}")
    if "default_branch" not in text or "main" not in text:error("catalog does not enforce main as the default branch")
elif REPOSITORY=="gitops":
    for p in list((ROOT/"applications").glob("*.yaml"))+list((ROOT/"projects").glob("*.yaml")):
        text=p.read_text("utf-8",errors="ignore")
        if re.search(r'(?m)^\s*(?:sourceRepos|destinations):\s*\[?\s*["\']?\*["\']?',text):
            error(f"wildcard Argo authority in {p.relative_to(ROOT)}")
    for p in ROOT.rglob("*.y*ml"):
        # Negative policy fixtures intentionally contain denied examples.
        if "tests" in p.parts or "testdata" in p.parts:
            continue
        text=p.read_text("utf-8",errors="ignore")
        if re.search(r'(?i)(?:image|newName|newTag):?[^\n]*(?::latest|newTag:\s*["\']?latest)',text):
            error(f"mutable image tag in {p.relative_to(ROOT)}")
        if re.search(r'(?m)^kind:\s*Secret\s*$',text) and re.search(r'(?m)^\s*(?:data|stringData):\s*$',text):
            error(f"plaintext Kubernetes Secret object in {p.relative_to(ROOT)}")
elif REPOSITORY=="infrastructure-live":
    for env in ("development","staging","production"):
        if not (ROOT/f"5-workloads/{env}").is_dir(): error(f"missing workload environment {env}")

    required_supply_chain = [
        "1-org/automation-iam",
        "1-org/common-projects",
        "5-workloads/development/supply-chain-iam",
        "5-workloads/staging/supply-chain-iam",
        "5-workloads/production/supply-chain-iam",
    ]
    for relative in required_supply_chain:
        if not (ROOT / relative).exists():
            error(f"missing supply-chain authority unit: {relative}")
    automation_text = "\n".join(
        path.read_text("utf-8", errors="ignore")
        for path in (ROOT / "1-org/automation-iam").rglob("*.tf")
    )
    for identity in ("artifact-builder", "artifact-qualifier", "artifact-signer", "artifact-promoter"):
        if identity not in automation_text:
            error(f"normal-plane supply-chain identity missing from automation-iam: {identity}")
    if "sa-attestor@" in "\n".join(
        path.read_text("utf-8", errors="ignore")
        for path in ROOT.rglob("*.hcl")
    ):
        error("legacy Ring-0 sa-attestor reference remains in live infrastructure")
    account_text = (ROOT / "account.hcl").read_text("utf-8", errors="ignore")
    if "buildkite_wif_pool_name" not in account_text:
        error("account contract does not require the bootstrap-managed Buildkite WIF pool")
    production_cpu = ROOT / "5-workloads/production/nodepools/cpu/terragrunt.hcl"
    if production_cpu.exists() and re.search(r"(?m)^\s*spot\s*=\s*true\s*$", production_cpu.read_text("utf-8", errors="ignore")):
        error("production CPU control-plane pool may not use Spot capacity")
    staging_cpu = ROOT / "5-workloads/staging/nodepools/cpu/terragrunt.hcl"
    if staging_cpu.exists() and re.search(r"(?m)^\s*spot\s*=\s*true\s*$", staging_cpu.read_text("utf-8", errors="ignore")):
        error("staging CPU control-plane pool must rehearse non-preemptible production capacity")
    for p in ROOT.rglob("*.hcl"):
        text=p.read_text("utf-8",errors="ignore")
        if "ANY_IDENTITY" in text:error(f"VPC-SC ANY_IDENTITY escape in {p.relative_to(ROOT)}")
        if re.search(r'(?<![0-9])0\.0\.0\.0/0(?![0-9])',text) and re.search(r'(?i)(master_authorized|control[_-]?plane|authorized[_-]?network)',text):
            error(f"broad control-plane CIDR in live configuration: {p.relative_to(ROOT)}")

if ERRORS:
    for msg in sorted(set(ERRORS)): print(f"ERROR: {msg}",file=sys.stderr)
    print(f"{len(set(ERRORS))} production contract violation(s)",file=sys.stderr)
    raise SystemExit(1)
print(f"{REPOSITORY}: production contract passed")
