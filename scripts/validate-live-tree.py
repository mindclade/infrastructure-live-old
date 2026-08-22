#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

#
"""Credential-free structural acceptance checks for infrastructure-live."""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []

for forbidden in (".terraform", ".terragrunt-cache"):
    for path in ROOT.rglob(forbidden):
        if ".git" not in path.parts:
            errors.append(f"forbidden cache: {path.relative_to(ROOT)}")
for path in ROOT.rglob("*"):
    if (
        not path.is_file()
        or ".git" in path.parts
        or path.name == "validate-live-tree.py"
    ):
        continue
    if path.name.startswith("._") or path.name == ".DS_Store":
        errors.append(f"metadata: {path.relative_to(ROOT)}")
    if re.search(r"terraform\.tfstate|\.tfplan$", path.name):
        errors.append(f"state/plan: {path.relative_to(ROOT)}")

if (
    ROOT.joinpath("CODEOWNERS").exists()
    or not ROOT.joinpath(".github/CODEOWNERS").is_file()
):
    errors.append("CODEOWNERS must exist only at .github/CODEOWNERS")


for required in (
    "1-org/automation-iam/terragrunt.hcl",
    "1-org/automation-iam/main.tf",
    "5-workloads/shared/control-plane-identities/terragrunt.hcl",
    "scripts/validate-account.py",
    "docs/automation-identity-handoff.md",
    "5-workloads/shared/production-qualification-evidence/terragrunt.hcl",
    "5-workloads/shared/production-qualification-evidence/.terraform.lock.hcl",
    "5-workloads/shared/production-qualification-access-logs/terragrunt.hcl",
    "5-workloads/shared/production-qualification-access-logs/.terraform.lock.hcl",
    "5-workloads/ci/bazel-remote-cache/terragrunt.hcl",
    "5-workloads/ci/bazel-remote-cache/.terraform.lock.hcl",
    "5-workloads/ci/bazel-remote-cache/README.md",
    "1-org/kms-dr-evidence/terragrunt.hcl",
):
    if not ROOT.joinpath(required).is_file():
        errors.append(f"missing control-plane handoff file: {required}")

control_plane = ROOT.joinpath("5-workloads/shared/control-plane-identities/main.tf")
if control_plane.is_file():
    control_text = control_plane.read_text(encoding="utf-8")
    if "github-app-terraform-pem" in control_text:
        errors.append(
            "normal infrastructure still owns the Ring-0 Terraform module-reader secret"
        )
    if "github-app-render-pem" not in control_text:
        errors.append(
            "GitOps render secret container is missing from normal security infrastructure"
        )

for environment in ("development", "staging", "production"):
    required = (
        "gke",
        "artifact-registry",
        "artifact-registry-dr",
        "binary-authorization",
        "workload-identities",
        "secret-manager",
        "observability",
        "backup-dr",
    )
    for unit in required:
        if not ROOT.joinpath(
            "5-workloads", environment, unit, "terragrunt.hcl"
        ).is_file():
            errors.append(f"missing {environment} workload unit: {unit}")
    if not ROOT.joinpath(
        "2-environments", environment, "kms-dr", "terragrunt.hcl"
    ).is_file():
        errors.append(f"missing {environment} recovery-region KMS unit")
    if ROOT.joinpath("5-workloads", environment, "argocd", "terragrunt.hcl").exists():
        errors.append(f"Terraform still owns Argo CD installation in {environment}")
    prereq = ROOT / "5-workloads" / environment / "argocd-prereqs"
    if (
        not prereq.joinpath("README.md").is_file()
        or prereq.joinpath("terragrunt.hcl").exists()
    ):
        errors.append(
            f"{environment}: argocd-prereqs must be a cloud handoff without an installer"
        )

    # GKE Gateway owns generated backend-service names. A live Terraform unit that copies
    # those names back into Ring 1 creates a backward dependency and can bind the wrong
    # backend. IAP enablement is a GCPBackendPolicy in GitOps; this directory is an explicit
    # activation gate until access IAM can consume stable outputs.
    iap = ROOT / "5-workloads" / environment / "iap-access"
    if (
        not iap.joinpath("README.md").is_file()
        or iap.joinpath("terragrunt.hcl").exists()
    ):
        errors.append(
            f"{environment}: iap-access must be a documented handoff without generated backend names"
        )


# No fictional/sample partner can enter the live run queue. Active partner units require a
# metadata record so legal/security ownership is reviewable independently of HCL.
partners = ROOT / "4-projects" / "partners"
if not partners.joinpath("README.md").is_file():
    errors.append("missing 4-projects/partners/README.md")
if partners.is_dir():
    for child in partners.iterdir():
        if not child.is_dir():
            continue
        if child.name in {"example", "acme", "sample", "template", "_template"}:
            errors.append(
                f"non-live partner identifier in live tree: {child.relative_to(ROOT)}"
            )
        if (
            child.joinpath("terragrunt.hcl").is_file()
            and not child.joinpath("partner.yaml").is_file()
        ):
            errors.append(
                f"active partner unit lacks partner.yaml metadata: {child.relative_to(ROOT)}"
            )

# Live source may not contain unresolved operational placeholders. Documentation and examples
# may explain placeholder shapes, but executable HCL/Terraform/workflows may not.
marker_words = (
    "REPLACE" + "_ME",
    "CHANGE" + "ME",
    "FIX" + "ME",
    "T" + "BD",
    "T" + "BC",
)
marker = re.compile(
    r"\b(?:" + "|".join(map(re.escape, marker_words)) + r"|YOUR_[A-Z0-9_]+)\b"
)
for path in ROOT.rglob("*"):
    if (
        not path.is_file()
        or ".git" in path.parts
        or path.name == "validate-live-tree.py"
    ):
        continue
    rel = path.relative_to(ROOT)
    if (
        "examples" in rel.parts
        or "docs" in rel.parts
        or path.suffix == ".md"
        or ".example" in path.name
    ):
        continue
    if path.suffix not in {".hcl", ".tf", ".yml", ".yaml", ".sh", ".py", ".toml"}:
        continue
    for line_number, line in enumerate(
        path.read_text(errors="ignore").splitlines(), start=1
    ):
        # Ignore pure comments; comments describing the validation rule itself are harmless.
        if line.lstrip().startswith(("#", "//")):
            continue
        if marker.search(line):
            errors.append(f"unresolved marker: {rel}:{line_number}")

for domain in ("mindclade-com", "mindclade-ai", "mindclade-dev", "mindclade-studio"):
    if not ROOT.joinpath(
        "3-networks/shared/public-zones", domain, "terragrunt.hcl"
    ).is_file():
        errors.append(f"missing authoritative DNS zone unit: {domain}")

version_pattern = re.compile(r'module_version\s*=\s*"(v\d+\.\d+\.\d+|[0-9a-f]{40})"')
for config in ROOT.rglob("terragrunt.hcl"):
    text = config.read_text(encoding="utf-8")
    if "module_source_base" in text and "source" in text:
        versions = re.findall(r'module_version\s*=\s*"([^"]+)"', text)
        if not versions or any(
            not version_pattern.fullmatch(f'module_version = "{v}"') for v in versions
        ):
            errors.append(
                f"mutable or missing module version: {config.relative_to(ROOT)}"
            )
        if "?ref=${local.module_version}" not in text:
            errors.append(
                f"module source is not pinned through module_version: {config.relative_to(ROOT)}"
            )

text = "\n".join(
    path.read_text(errors="ignore")
    for path in ROOT.rglob("*")
    if path.is_file()
    and ".git" not in path.parts
    and path.name not in {"BLUEPRINT.md", "validate-live-tree.py"}
)
for stale in (
    "mindclade-org",
    "github.com/mindclade/mindclade.git",
    "include.root.locals.folder_ids",
    "audit_project_id =",
    "3-networks/private-service-connect",
    "docs/module-interface-gap.md",
):
    if stale in text:
        errors.append(f"stale ownership/reference: {stale}")

if errors:
    for message in sorted(set(errors)):
        print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)
print("live-tree invariants passed")
