#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# MINDCLADE CONFIDENTIAL - PROPRIETARY AND TRADE SECRET
# Copyright (c) 2026 Mindclade. All rights reserved.
"""Validate the Mindclade production repository contract.

This check intentionally uses only the Python standard library.
"""

from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "infrastructure-live"
QUARANTINE_MODULE_REF = "4d5c0105295bf4a01b770fb75f6a8db5c22c8f79"
CONTRACT = json.loads(
    '{"authority": ["normal-gcp-organization-infrastructure", "folders", "org-policy", "environments", "networks", "projects", "gke", "managed-cloud-services"], "forbidden_authority": ["ring0-state-foundation", "argocd-installation", "kubernetes-desired-state", "application-source"], "forbidden_paths": [".terraform", ".terragrunt-cache", "5-workloads/development/argocd", "5-workloads/staging/argocd", "5-workloads/production/argocd"], "repository_class": "production-control", "required_paths": ["AGENTS.md", "1-org", "2-environments/development", "2-environments/staging", "2-environments/production", "3-networks", "4-projects", "5-workloads/development", "5-workloads/staging", "5-workloads/production", "root.hcl"], "visibility": "private"}'
)
ERRORS = []


def error(msg):
    ERRORS.append(msg)


def repository_paths() -> list[Path]:
    """Return version-controlled paths in a checkout, or all paths in an exported tree."""
    if (ROOT / ".git").exists():
        result = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            check=True,
            capture_output=True,
        )
        return [
            ROOT / raw.decode("utf-8", errors="surrogateescape")
            for raw in result.stdout.split(b"\0")
            if raw
        ]
    return list(ROOT.rglob("*"))


TRACKED_PATHS = repository_paths()
TRACKED_RELATIVE = {p.relative_to(ROOT).as_posix() for p in TRACKED_PATHS}
LEGACY_GITHUB_IDENTITIES = (
    "Mind" + "clade/",
    "github.com/" + "Mind" + "clade",
    "/orgs/" + "Mind" + "clade",
)


def tracked_prefix_exists(relative: str) -> bool:
    prefix = relative.rstrip("/")
    return prefix in TRACKED_RELATIVE or any(
        path.startswith(prefix + "/") for path in TRACKED_RELATIVE
    )


repository_contract = (ROOT / "contracts/repository.yaml").read_text(
    "utf-8", errors="ignore"
)
for canonical_url in (
    "https://github.com/enterprises/mindclade",
    "https://github.com/mindclade",
    "https://github.com/orgs/mindclade/repositories",
    f"https://github.com/mindclade/{REPOSITORY}",
):
    if canonical_url not in repository_contract:
        error(f"repository contract omits canonical GitHub URL: {canonical_url}")

makefile = (ROOT / "Makefile").read_text("utf-8", errors="ignore")
module_contract_docs = (ROOT / "docs/module-interface-contract.md").read_text(
    "utf-8", errors="ignore"
)
for required_make_contract in (
    "validate-integration: validate validate-module-interfaces validate-capacity-contract",
    "validate-source-integration: validate validate-module-candidate validate-capacity-candidate",
    'python3 scripts/validate-module-interfaces.py --monorepo "$(MONOREPO)"',
    'python3 scripts/validate-module-interfaces.py --monorepo "$(MONOREPO)" --candidate-version "$(CANDIDATE_MODULE_VERSION)"',
    'python3 scripts/validate-capacity-contract.py --monorepo "$(MONOREPO)"',
    'python3 scripts/validate-capacity-contract.py --monorepo "$(MONOREPO)" --candidate-version "$(CANDIDATE_MODULE_VERSION)"',
):
    if required_make_contract not in makefile:
        error(
            "local cross-repository module validation omits: "
            + required_make_contract
        )
if (
    "make validate-integration MONOREPO=../mindclade-internal-monorepo"
    not in module_contract_docs
):
    error("module interface documentation omits the executable integration target")
if (
    "make validate-source-integration MONOREPO=../mindclade-internal-monorepo"
    not in module_contract_docs
):
    error("module interface documentation omits the planned-source integration target")

for rel in CONTRACT["required_paths"]:
    if not (ROOT / rel).exists():
        error(f"missing required path: {rel}")
for rel in CONTRACT["forbidden_paths"]:
    if tracked_prefix_exists(rel):
        error(f"forbidden tracked path present: {rel}")
for p in TRACKED_PATHS:
    relative = p.relative_to(ROOT)
    if any(
        part in {".terraform", ".terragrunt-cache", "__MACOSX", "__pycache__"}
        for part in relative.parts
    ):
        error(f"local/cache artifact is tracked: {relative}")
    if (
        p.name.startswith("._")
        or ".tfstate" in p.name
        or p.suffix in {".pyc", ".tfplan"}
    ):
        error(f"generated/sensitive artifact is tracked: {relative}")
    if p.is_symlink():
        error(f"symlink forbidden in delivery: {relative}")
    if p.is_file() and p.stat().st_size <= 2_000_000:
        text = p.read_text("utf-8", errors="ignore")
        if any(legacy in text for legacy in LEGACY_GITHUB_IDENTITIES):
            error(f"noncanonical GitHub organization identity in {relative}")

# GitHub Actions must be immutable and least privilege.
for p in (
    (ROOT / ".github/workflows").glob("*.y*ml")
    if (ROOT / ".github/workflows").exists()
    else []
):
    text = p.read_text("utf-8", errors="ignore")
    for use in re.findall(r"(?m)^\s*-?\s*uses:\s*([^#\s]+)", text):
        if use.startswith("./"):
            continue
        if not (
            re.search(r"@[0-9a-f]{40}$", use)
            or re.search(r"@sha256:[0-9a-f]{64}$", use)
            or re.fullmatch(
                r"mindclade/\.github/\.github/workflows/[^@]+@v[0-9]+\.[0-9]+\.[0-9]+",
                use,
            )
        ):
            error(
                f"workflow action is not immutable-pinned in {p.relative_to(ROOT)}: {use}"
            )
    if "permissions:" not in text:
        error(f"workflow lacks explicit permissions: {p.relative_to(ROOT)}")

# No obvious plaintext credentials. Values are intentionally conservative.
secret_patterns = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
]
for p in TRACKED_PATHS:
    if not p.is_file() or p.stat().st_size > 2_000_000:
        continue
    try:
        text = p.read_text("utf-8", errors="ignore")
    except OSError:
        continue
    for pattern in secret_patterns:
        if pattern.search(text):
            error(f"possible credential in {p.relative_to(ROOT)}")

if REPOSITORY == "bootstrap":
    for forbidden in ("modules/folders", "modules/governance"):
        if (ROOT / forbidden).exists():
            error(f"Ring-0 boundary violation: {forbidden}")
    combined = "\n".join(
        p.read_text("utf-8", errors="ignore") for p in ROOT.rglob("*.tf")
    )
    if re.search(r'module\s+"(?:folders|governance)"', combined):
        error("Ring-0 root still instantiates folders/governance")
elif REPOSITORY == "github-config":
    text = (ROOT / "catalog/repositories.yaml").read_text("utf-8", errors="ignore")
    for repo in (
        ".github",
        "bootstrap",
        "github-config",
        "infrastructure-live",
        "gitops",
        "mindclade-internal-monorepo",
    ):
        if repo not in text:
            error(f"repository catalog missing {repo}")
    if "default_branch" not in text or "main" not in text:
        error("catalog does not enforce main as the default branch")
elif REPOSITORY == "gitops":
    for p in list((ROOT / "applications").glob("*.yaml")) + list(
        (ROOT / "projects").glob("*.yaml")
    ):
        text = p.read_text("utf-8", errors="ignore")
        if re.search(
            r'(?m)^\s*(?:sourceRepos|destinations):\s*\[?\s*["\']?\*["\']?', text
        ):
            error(f"wildcard Argo authority in {p.relative_to(ROOT)}")
    for p in ROOT.rglob("*.y*ml"):
        # Negative policy fixtures intentionally contain denied examples.
        if "tests" in p.parts or "testdata" in p.parts:
            continue
        text = p.read_text("utf-8", errors="ignore")
        if re.search(
            r'(?i)(?:image|newName|newTag):?[^\n]*(?::latest|newTag:\s*["\']?latest)',
            text,
        ):
            error(f"mutable image tag in {p.relative_to(ROOT)}")
        if re.search(r"(?m)^kind:\s*Secret\s*$", text) and re.search(
            r"(?m)^\s*(?:data|stringData):\s*$", text
        ):
            error(f"plaintext Kubernetes Secret object in {p.relative_to(ROOT)}")
elif REPOSITORY == "infrastructure-live":
    for env in ("development", "staging", "production"):
        if not (ROOT / f"5-workloads/{env}").is_dir():
            error(f"missing workload environment {env}")

    module_refs: dict[str, str] = {}
    for path in TRACKED_PATHS:
        if path.suffix != ".hcl" or not path.is_file():
            continue
        match = re.search(
            r'\bmodule_version\s*=\s*"([^"]+)"',
            path.read_text("utf-8", errors="ignore"),
        )
        if match:
            module_refs[path.relative_to(ROOT).as_posix()] = match.group(1)
    if not module_refs:
        error("live tree has no immutable module-version pins")
    for relative, module_ref in sorted(module_refs.items()):
        if module_ref != QUARANTINE_MODULE_REF:
            error(
                f"live module pin differs from quarantine bridge in {relative}: "
                f"{module_ref}"
            )
    dns_inventory = json.loads(
        (ROOT / "contracts/dns-domain-inventory.json").read_text("utf-8")
    )
    if dns_inventory.get("module_contract", {}).get("ref") != QUARANTINE_MODULE_REF:
        error("DNS module contract differs from the quarantine bridge commit")

    required_supply_chain = [
        "1-org/automation-iam",
        "1-org/common-projects",
    ]
    for relative in required_supply_chain:
        if not (ROOT / relative).exists():
            error(f"missing supply-chain authority unit: {relative}")
    automation_text = "\n".join(
        path.read_text("utf-8", errors="ignore")
        for path in (ROOT / "1-org/automation-iam").rglob("*.tf")
    )
    for identity in (
        "artifact-builder",
        "artifact-qualifier",
        "artifact-signer",
        "artifact-promoter",
    ):
        if identity not in automation_text:
            error(
                f"normal-plane supply-chain identity missing from automation-iam: {identity}"
            )
    if "var.buildkite_wif_enabled ?" not in automation_text:
        error("retired Buildkite identities are not fail-closed behind the v1.2 flag")
    for deferred_identity in (
        "arc-canary",
        "artifact-qual-reader",
        "artifact_release_identities",
        "dr_evidence_identity",
    ):
        if deferred_identity in automation_text:
            error(f"deferred v4 identity remains active in automation-iam: {deferred_identity}")
    if "sa-attestor@" in "\n".join(
        path.read_text("utf-8", errors="ignore") for path in ROOT.rglob("*.hcl")
    ):
        error("legacy Ring-0 sa-attestor reference remains in live infrastructure")

    cost_workflow = (ROOT / ".github/workflows/cost.yml").read_text(
        "utf-8", errors="ignore"
    )
    drift_workflow = (ROOT / ".github/workflows/drift.yml").read_text(
        "utf-8", errors="ignore"
    )
    if not re.search(r"(?m)^\s{4}environment:\s*plan\s*$", cost_workflow):
        error("cost workflow cannot satisfy the exact plan-environment OIDC subject")
    if "if: github.ref == 'refs/heads/main'" not in drift_workflow:
        error(
            "scheduled/manual drift authentication is not restricted to protected main"
        )
    if (
        "INFRASTRUCTURE_CONNECTED_DRIFT" not in drift_workflow
        or drift_workflow.count(
            "needs.readiness.outputs.enabled == 'true'"
        )
        != 3
    ):
        error(
            "connected drift does not retain the explicit post-bootstrap activation boundary"
        )

    automation_main = (ROOT / "1-org/automation-iam/main.tf").read_text(
        "utf-8", errors="ignore"
    )
    automation_outputs = (ROOT / "1-org/automation-iam/outputs.tf").read_text(
        "utf-8", errors="ignore"
    )
    if 'resource "google_service_account_iam_member" "artifact_signer_github_wif"' not in automation_main:
        error("v3 artifact signer is not bound to the bootstrap-exported GitHub principal")
    for trust_value in (
        "gh-mindclade-internal-monorepo",
        "reusable-binauthz-sign.yml",
        "@refs/tags/v3.0.0",
    ):
        if trust_value not in automation_main:
            error(f"v3 artifact signer trust check omits: {trust_value}")
    for output_name in (
        "WIF_PROVIDER_SIGNER",
        "SA_ARTIFACT_SIGNER",
        "ARTIFACT_SIGNER_PRINCIPAL",
        "ARTIFACT_SIGNER_JOB_WORKFLOW_REF",
    ):
        if output_name not in automation_outputs:
            error(f"artifact signer identity output omits: {output_name}")

    control_plane_outputs = (
        ROOT / "5-workloads/shared/control-plane-identities/outputs.tf"
    ).read_text("utf-8", errors="ignore")
    identity_handoff_docs = (ROOT / "docs/automation-identity-handoff.md").read_text(
        "utf-8", errors="ignore"
    )
    for output_name in ("SA_GITOPS_RENDER", "SA_GITOPS_VERIFIER"):
        if output_name not in control_plane_outputs:
            error(f"GitOps control-plane identity output omits: {output_name}")
        if output_name not in identity_handoff_docs:
            error(f"GitOps identity handoff documentation omits: {output_name}")
    if "github_config_identity_handoff" not in control_plane_outputs:
        error(
            "GitOps control-plane identities lack a stable github-config output contract"
        )
    if "reapply `github-config`" not in identity_handoff_docs:
        error(
            "GitOps identity handoff does not require github-config re-export/reapply"
        )
    handoff_exporter_path = ROOT / "scripts/export-applied-control-plane-handoff.py"
    handoff_schema_path = ROOT / "contracts/applied-control-plane-handoff.schema.json"
    if not handoff_exporter_path.is_file():
        error("missing applied control-plane handoff exporter")
    if not handoff_schema_path.is_file():
        error("missing applied control-plane handoff schema")
    if handoff_exporter_path.is_file():
        handoff_exporter = handoff_exporter_path.read_text(
            "utf-8", errors="ignore"
        )
        for required_handoff_gate in (
            "artifact_signer_identity_contract",
            "SA_ARTIFACT_SIGNER",
            "github_config_identity_handoff",
            "SA_GITOPS_RENDER",
            "SA_GITOPS_VERIFIER",
            '"project_id"',
            '"attestor_names"',
            '"attestor_key_versions"',
            '"DRYRUN_AUDIT_LOG_ONLY"',
            '"binary_authorization": "audit-only"',
            '"arc_activation": "disabled"',
            '"deployment-attestor"',
            "infrastructure-live source tree must be clean before export",
            "source commit differs from --expected-source-commit",
            "applied handoff evidence must be written outside the repository",
        ):
            if required_handoff_gate not in handoff_exporter:
                error(
                    "applied control-plane handoff exporter omits: "
                    f"{required_handoff_gate}"
                )
    if "export-applied-control-plane-handoff.py" not in identity_handoff_docs:
        error("GitOps identity handoff does not invoke the applied-output exporter")
    control_plane_iam = (
        ROOT / "5-workloads/shared/control-plane-identities/main.tf"
    ).read_text("utf-8", errors="ignore")
    if "roles/binaryauthorization.attestorsVerifier" not in control_plane_iam:
        error(
            "GitOps verifier cannot cryptographically validate deployment attestations"
        )
    if "roles/binaryauthorization.attestorsViewer" in control_plane_iam:
        error("GitOps verifier retains list-only Binary Authorization access")
    for environment in ("development", "staging", "production"):
        if (ROOT / f"5-workloads/{environment}/supply-chain-iam").exists():
            error(f"{environment} retains deferred artifact-release IAM activation")
    all_binauthz = "\n".join(
        (ROOT / f"5-workloads/{env}/binary-authorization/terragrunt.hcl").read_text(
            "utf-8", errors="ignore"
        )
        for env in ("development", "staging", "production")
    )
    if "cluster_admission_rules" in all_binauthz:
        error("Binary Authorization live units retain unsupported pseudo-namespace cluster rules")
    if "ALWAYS_ALLOW" in all_binauthz:
        error("Binary Authorization live units retain an ALWAYS_ALLOW bypass")
    for deferred_attestor in ("build-attestor", "qualification-attestor"):
        if not re.search(
            rf"(?m)^\s*{re.escape(deferred_attestor)}\s*=\s*\[\]\s*$",
            all_binauthz,
        ):
            error(f"{deferred_attestor} must have no active issuer while v4 is deferred")
    signer_binding = re.search(
        r'(?m)^\s*deployment-attestor\s*=\s*\["serviceAccount:\$\{dependency\.automation\.outputs\.supply_chain_service_accounts\["([a-z]+)"\]\}"\]\s*$',
        all_binauthz,
    )
    if not signer_binding or signer_binding.group(1) != "signer":
        error("deployment-attestor is not bound exclusively to the retained v3 signer")
    if "vuln-scan-attestor" in all_binauthz:
        error(
            "legacy vulnerability attestor remains; vulnerability belongs to independent qualification"
        )
    binauthz_defaults = (ROOT / "_envcommon/binauthz.hcl").read_text(
        "utf-8", errors="ignore"
    )
    for required in (
        'jsondecode(file("${get_repo_root()}/contracts/argocd-image-exceptions.json"))',
        "exempt_images                 = local.argocd_exception_images",
        'global_policy_evaluation_mode = "ENABLE"',
    ):
        if required not in binauthz_defaults:
            error(f"Binary Authorization exact-exception contract omits: {required}")
    for forbidden in (
        "gcr.io/google-containers/*",
        "k8s.gcr.io/**",
        "registry.k8s.io/**",
        "gke.gcr.io/**",
    ):
        if forbidden in binauthz_defaults:
            error(f"Binary Authorization retains broad image exemption: {forbidden}")
    if not re.search(
        r'enforcement_mode\s*=\s*"DRYRUN_AUDIT_LOG_ONLY"', binauthz_defaults
    ) or "ENFORCED_BLOCK_AND_AUDIT_LOG" in binauthz_defaults:
        error("Binary Authorization must remain audit-only while v4 is deferred")
    admission = re.search(
        r"require_attestations_by\s*=\s*local\.environment\s*==\s*\"production\"\s*\?\s*\[(.*?)\]\s*:\s*\[(.*?)\]",
        binauthz_defaults,
        re.S,
    )
    if not admission:
        error("Binary Authorization environment admission contract is not parseable")
    else:
        production_attestors = set(
            re.findall(r"\"([^\"]+-attestor)\"", admission.group(1))
        )
        lower_attestors = set(re.findall(r"\"([^\"]+-attestor)\"", admission.group(2)))
        if production_attestors != {"deployment-attestor"}:
            error("global production admission must require deployment-attestor only")
        if lower_attestors != {"build-attestor"}:
            error("lower environments must use the build-attestor trust root")

    exception_validator = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate-argocd-image-exceptions.py")],
        text=True,
        capture_output=True,
        check=False,
    )
    if exception_validator.returncode != 0:
        error(
            "Argo exact-digest exception contract failed: "
            + exception_validator.stderr.strip()
        )

    account_text = (ROOT / "account.hcl").read_text("utf-8", errors="ignore")
    for deferred_variable in (
        "ARTIFACT_RELEASE_IDENTITIES_JSON",
        "DR_EVIDENCE_IDENTITY_JSON",
    ):
        if deferred_variable in account_text:
            error(f"account contract retains deferred v4 input: {deferred_variable}")
    if 'get_env("BUILDKITE_WIF_ENABLED", "false")' not in account_text:
        error("account contract does not default retired Buildkite federation to disabled")
    if 'get_env("CLOUD_IDENTITY_CUSTOMER_ID")' not in account_text:
        error("account contract omits the immutable Cloud Identity customer ID")
    if 'get_env("ORG_POLICY_ACTIVATION_PHASE", "baseline")' not in account_text:
        error(
            "account contract does not fail safe to baseline-only org-policy adoption"
        )
    bootstrap_account = (ROOT / "scripts/bootstrap-account.py").read_text(
        "utf-8", errors="ignore"
    )
    if (
        "validated_buildkite" not in bootstrap_account
        or 'contract.get("contract_version") != "1.2.0"' not in bootstrap_account
        or '"WIF_PROVIDER_SIGNER"' not in bootstrap_account
        or '"ARTIFACT_SIGNER_PRINCIPAL"' not in bootstrap_account
        or '"ARTIFACT_SIGNER_JOB_WORKFLOW_REF"' not in bootstrap_account
        or "ARTIFACT_RELEASE_IDENTITIES_JSON" in bootstrap_account
        or "DR_EVIDENCE_IDENTITY_JSON" in bootstrap_account
    ):
        error("bootstrap account exporter differs from the deployed v1.2 signer contract")
    initial_import = (ROOT / "docs/initial-import.md").read_text(
        "utf-8", errors="ignore"
    )
    for required in (
        "scripts/classify-state-prefix.py",
        "state_list_status=$?",
        "One or more URLs matched no objects.",
        "permission, authentication, network, retention, or metadata-read error",
        "Resume after a completed import",
        "resume_verified_import",
        "must not be imported again",
        "state generation changed after the stopped import",
    ):
        if required not in initial_import:
            error(f"initial import fresh-prefix guard omits: {required}")
    flake = (ROOT / "flake.nix").read_text("utf-8", errors="ignore")
    pinned_tf_path = 'TG_TF_PATH = "${terraformPinned}/bin/terraform";'
    if flake.count(pinned_tf_path) != 2:
        error("both Nix dev shells must pin Terragrunt to the exact Terraform derivation")
    for required in ("TG_TF_PATH", "skip_outputs", "baseline"):
        if required not in initial_import:
            error(f"initial import runtime guard omits: {required}")
    if (
        '"platform_contract"' not in bootstrap_account
        or '"output"' not in bootstrap_account
        or 'contract.get("contract_version") != "1.2.0"' not in bootstrap_account
    ):
        error(
            "bootstrap account exporter bypasses the versioned Ring-0 platform contract"
        )
    if '"CLOUD_IDENTITY_CUSTOMER_ID"' not in bootstrap_account:
        error(
            "bootstrap account exporter omits the operator-verified Cloud Identity customer ID"
        )
    if '"ORG_POLICY_ACTIVATION_PHASE": "baseline"' not in bootstrap_account:
        error(
            "bootstrap account exporter does not preserve baseline-only policy adoption"
        )
    production_cpu = ROOT / "5-workloads/production/nodepools/cpu/terragrunt.hcl"
    if production_cpu.exists() and re.search(
        r"(?m)^\s*spot\s*=\s*true\s*$",
        production_cpu.read_text("utf-8", errors="ignore"),
    ):
        error("production CPU control-plane pool may not use Spot capacity")
    staging_cpu = ROOT / "5-workloads/staging/nodepools/cpu/terragrunt.hcl"
    if staging_cpu.exists() and re.search(
        r"(?m)^\s*spot\s*=\s*true\s*$", staging_cpu.read_text("utf-8", errors="ignore")
    ):
        error(
            "staging CPU control-plane pool must rehearse non-preemptible production capacity"
        )
    for p in ROOT.rglob("*.hcl"):
        text = p.read_text("utf-8", errors="ignore")
        if "ANY_IDENTITY" in text:
            error(f"VPC-SC ANY_IDENTITY escape in {p.relative_to(ROOT)}")

    # The pinned network module deletes Google's implicit route and recreates a protected,
    # explicit route when create_default_internet_route is true (its default). No caller may
    # disable that contract for a VPC that uses Public Cloud NAT.
    for environment in ("development", "staging", "production"):
        vpc = (
            ROOT / f"3-networks/{environment}/shared-vpc-host/terragrunt.hcl"
        ).read_text("utf-8", errors="ignore")
        if re.search(
            r"(?m)^\s*create_default_internet_route\s*=\s*false\s*$", vpc
        ):
            error(f"{environment} VPC disables the protected default internet route")
    for deferred_unit in (
        "1-org/kms-dr-evidence",
        "3-networks/ci/arc-vpc",
        "5-workloads/ci/arc-gke",
        "5-workloads/ci/binary-authorization",
        "5-workloads/shared/dr-evidence-access-logs",
        "5-workloads/shared/dr-evidence",
    ):
        if (ROOT / deferred_unit).exists():
            error(f"deferred ARC/DR unit remains active: {deferred_unit}")
    for env in ("development", "staging", "production"):
        firewall_path = ROOT / f"3-networks/{env}/firewall-baseline/terragrunt.hcl"
        firewall = firewall_path.read_text("utf-8", errors="ignore")
        deny = re.search(r"(?s)deny-egress-default\s*=\s*\{(.*?)\n\s*\}", firewall)
        if not deny or not re.search(
            r'destination_ranges\s*=\s*\["0\.0\.0\.0/0"\]', deny.group(1)
        ):
            error(f"{env} firewall does not deny all unmatched IPv4 egress")
        control_plane = re.search(
            r"(?s)allow-control-plane-webhooks\s*=\s*\{(.*?)\n\s*\}", firewall
        )
        if control_plane and "0.0.0.0/0" in control_plane.group(1):
            error(f"{env} firewall permits a broad control-plane CIDR")
        if "199.36.153.4/30" not in firewall or "34.126.0.0/18" not in firewall:
            error(
                f"{env} firewall lacks the restricted Google API/direct-connect ranges"
            )

    dns = (ROOT / "3-networks/shared/dns-hub/terragrunt.hcl").read_text(
        "utf-8", errors="ignore"
    )
    for required in (
        'domain     = "googleapis.com."',
        'rrdatas = ["restricted.googleapis.com."]',
        "199.36.153.4",
    ):
        if required not in dns:
            error(f"restricted Google API DNS contract missing: {required}")
    if "network_self_links" in dns:
        error(
            "DNS hub consumes stale network_self_links output instead of network_self_link"
        )

    org_policy = (ROOT / "1-org/org-policies/terragrunt.hcl").read_text(
        "utf-8", errors="ignore"
    )
    for required in (
        'baseline_org_policy_adoption = get_env("ORG_POLICY_ACTIVATION_PHASE", "") == "baseline"',
        "skip_outputs = local.baseline_org_policy_adoption",
        "mock_outputs = local.baseline_org_policy_adoption ? {",
        "mock_outputs_allowed_terraform_commands = local.baseline_org_policy_adoption ? [",
    ):
        if required not in org_policy:
            error(f"organization-policy baseline dependency guard omits: {required}")
    if "skip_outputs = true" in org_policy:
        error("organization-policy folders dependency bypass is not phase-scoped")
    mock_commands_match = re.search(
        r"mock_outputs_allowed_terraform_commands\s*=\s*"
        r"local\.baseline_org_policy_adoption\s*\?\s*\[(.*?)\]\s*:\s*\[\]",
        org_policy,
        re.S,
    )
    expected_mock_commands = {"import", "init", "plan", "show", "validate"}
    if not mock_commands_match:
        error("organization-policy baseline mock-command allowlist is not parseable")
    else:
        actual_mock_commands = set(
            re.findall(r'"([a-z-]+)"', mock_commands_match.group(1))
        )
        if actual_mock_commands != expected_mock_commands:
            error(
                "organization-policy baseline mock commands must be exactly "
                f"{sorted(expected_mock_commands)}; got {sorted(actual_mock_commands)}"
            )
    if "https://agent.buildkite.com" in org_policy:
        error("organization WIF issuer policy retains the retired Buildkite issuer")
    for constraint in (
        "iam.managed.disableServiceAccountKeyCreation",
        "iam.disableServiceAccountKeyUpload",
        "iam.automaticIamGrantsForDefaultServiceAccounts",
        "iam.allowedPolicyMemberDomains",
        "storage.uniformBucketLevelAccess",
        "storage.publicAccessPrevention",
        "compute.vmExternalIpAccess",
        "essentialcontacts.managed.allowedContactDomains",
        "compute.managed.restrictProtocolForwardingCreationForTypes",
    ):
        if constraint not in org_policy:
            error(f"normal-plane organization-policy baseline omits {constraint}")
    for legacy_constraint in (
        '"iam.disableServiceAccountKeyCreation"',
        '"essentialcontacts.allowedContactDomains"',
        '"compute.restrictProtocolForwardingCreationForTypes"',
    ):
        if legacy_constraint in org_policy:
            error(
                "organization policy uses a legacy equivalent instead of the live managed "
                f"constraint: {legacy_constraint}"
            )
    policy_module = (ROOT / "1-org/org-policies/module/main.tf").read_text(
        "utf-8", errors="ignore"
    )
    for required in (
        'resource "google_org_policy_policy" "managed"',
        "parameters =",
        "length(each.value.allowed_values) == 0 ? null",
        "length(each.value.denied_values) == 0 ? null",
        "prevent_destroy = true",
    ):
        if required not in policy_module:
            error(f"organization-policy v2 adoption module omits: {required}")
    policy_variables = (
        ROOT / "1-org/org-policies/module/variables.tf"
    ).read_text("utf-8", errors="ignore")
    for required in (
        'length(var.list_policies["iam.allowedPolicyMemberDomains"].allowed_values) == 1',
        'var.list_policies["iam.allowedPolicyMemberDomains"].allowed_values[0] == var.cloud_identity_customer_id',
        'length(var.list_policies["iam.allowedPolicyMemberDomains"].denied_values) == 0',
    ):
        if required not in policy_variables:
            error(
                "domain-restricted-sharing policy does not require the exact "
                f"Cloud Identity customer: {required}"
            )
    if (
        'allowed_values == [var.cloud_identity_customer_id]'
        in policy_variables
    ):
        error(
            "domain-restricted-sharing check compares a list value to a tuple literal"
        )
    for required in (
        'allowedDomains = ["@${include.root.locals.domain}"]',
        'allowedSchemes = ["INTERNAL"]',
        'include.root.locals.org_policy_activation_phase == "extended"',
        'sandbox_external_ip_reset = include.root.locals.org_policy_activation_phase == "extended"',
    ):
        if required not in org_policy:
            error(f"organization-policy staged-adoption contract omits: {required}")
    for workflow_name in ("plan.yml", "apply.yml", "drift.yml", "cost.yml"):
        workflow = (ROOT / ".github/workflows" / workflow_name).read_text(
            "utf-8", errors="ignore"
        )
        for required_variable in (
            "CLOUD_IDENTITY_CUSTOMER_ID",
            "ORG_POLICY_ACTIVATION_PHASE",
        ):
            if (
                f"{required_variable}: ${{{{ vars.{required_variable} }}}}"
                not in workflow
            ):
                error(f"{workflow_name} omits governed variable: {required_variable}")
    if not re.search(r'"compute\.vmCanIpForward"\s*=\s*true', org_policy):
        error(
            "organization-policy baseline does not enforce the IP-forwarding prohibition"
        )
    if "bootstrap applies" in org_policy or "set in bootstrap" in org_policy:
        error("normal organization-policy authority is still attributed to Ring 0")
    contacts = (ROOT / "1-org/essential-contacts/terragrunt.hcl").read_text(
        "utf-8", errors="ignore"
    )
    if '"organizations/${include.root.locals.org_id}"' not in contacts:
        error("Essential Contacts unit omits organization-level routing")
    for address in ("security@", "platform@", "billing@", "legal@"):
        if address not in contacts:
            error(f"organization Essential Contacts omit governed group: {address}")

    for env in ("staging", "production"):
        binauthz = (
            ROOT / f"5-workloads/{env}/binary-authorization/terragrunt.hcl"
        ).read_text("utf-8", errors="ignore")
        if '"research-scratch"' in binauthz:
            error(f"{env} Binary Authorization retains a research-scratch bypass")
        perimeter = (
            ROOT / f"5-workloads/{env}/vpc-sc-perimeter/terragrunt.hcl"
        ).read_text("utf-8", errors="ignore")
        if not re.search(
            r"(?m)^\s*use_explicit_dry_run_spec\s*=\s*true\s*$", perimeter
        ):
            error(f"{env} VPC-SC must remain dry-run until its acceptance drill passes")
        for project in (
            "dependency.observability.outputs.project_number",
            "dependency.security.outputs.project_number",
        ):
            if project not in perimeter:
                error(f"{env} VPC-SC omits protected project: {project}")

    account_contract = (ROOT / "account.hcl").read_text("utf-8", errors="ignore")
    if 'get_env("GPU_ZONE"' not in account_contract:
        error("account contract lacks an explicit GPU/Parallelstore zone")
    gpu_profiles = {
        "gpu-a3": "gke-h100-a3-megagpu-8g",
        # The directory name is a retained Terragrunt state address; the selected
        # production profile is B200 A4 High.
        "gpu-a4": "gke-b200-a4-highgpu-8g",
    }
    for env in ("development", "staging", "production"):
        for pool, profile in gpu_profiles.items():
            gpu = (
                ROOT / f"5-workloads/{env}/nodepools/{pool}/terragrunt.hcl"
            ).read_text("utf-8", errors="ignore")
            if "account_vars.locals.gpu_zone" not in gpu:
                error(f"{env}/{pool} is not tied to the account GPU zone contract")
            if not re.search(rf'profile\s*=\s*"{re.escape(profile)}"', gpu):
                error(f"{env}/{pool} does not select the qualified {profile} contract")
            if profile in {
                "gke-h200-a3-ultragpu-8g",
                "gke-b200-a4-highgpu-8g",
            } and not re.search(
                r'capacity_mode\s*=\s*"QUEUED_PROVISIONING"', gpu
            ):
                error(f"{env}/{pool} high-density GPU capacity must use queued provisioning")
            if profile in {
                "gke-h200-a3-ultragpu-8g",
                "gke-b200-a4-highgpu-8g",
            } and not re.search(
                r'enable_compact_placement\s*=\s*false', gpu
            ):
                error(f"{env}/{pool} queued GPU capacity must disable compact placement")

    gpu_defaults = (ROOT / "_envcommon/gpu-nodepool.hcl").read_text(
        "utf-8", errors="ignore"
    )
    if not re.search(r"(?m)^\s*total_min_nodes\s*=\s*0\s*$", gpu_defaults):
        error("GPU pools must share a scale-to-zero minimum")

    selector = (ROOT / "scripts/select-apply-scopes.py").read_text(
        "utf-8", errors="ignore"
    )
    if (
        '"foundation": ("1-org/", "3-networks/shared/", "5-workloads/shared/")'
        not in selector
    ):
        error(
            "shared control-plane identities are not assigned to foundation authority"
        )

    for workflow_name in ("plan.yml", "drift.yml"):
        workflow = (ROOT / f".github/workflows/{workflow_name}").read_text(
            "utf-8", errors="ignore"
        )
        for days in re.findall(r"retention-days:\s*(\d+)", workflow):
            if int(days) > 1:
                error(
                    f"{workflow_name} retains sensitive Terraform evidence longer than one day"
                )
    plan_workflow = (ROOT / ".github/workflows/plan.yml").read_text(
        "utf-8", errors="ignore"
    )
    if (
        "- name: Validate account contract source\n"
        "        run: python3 scripts/validate-account.py\n"
    ) not in plan_workflow:
        error("unprivileged PR validation does not use the source-only account gate")
    if plan_workflow.count("python3 scripts/validate-account.py --runtime") != 1:
        error("protected plan must retain exactly one runtime account gate")
    if "  merge_group:" not in plan_workflow:
        error("plan workflow does not report a merge-queue check")
    if "    environment: plan" not in plan_workflow:
        error("cloud-backed PR plans are not gated by the plan environment")
    if "cat plan-output.txt" in plan_workflow:
        error("plan workflow publishes sensitive raw plan output into pull requests")
    terraform_version = (
        (ROOT / ".terraform-version").read_text("utf-8", errors="ignore").strip()
    )
    if terraform_version != "1.15.9":
        error("Terraform pin must name the current qualified 1.15.9 release")
    for workflow_name in ("apply.yml", "cost.yml", "drift.yml", "plan.yml"):
        workflow = (ROOT / f".github/workflows/{workflow_name}").read_text(
            "utf-8", errors="ignore"
        )
        if f'TF_VERSION: "{terraform_version}"' not in workflow:
            error(f"{workflow_name} Terraform version differs from .terraform-version")
    flake = (ROOT / "flake.nix").read_text("utf-8", errors="ignore")
    for terraform_pin in (
        'terraformVersion = "1.15.9"',
        'x86_64-linux = "sha256-du3Qsi0vJ9PS4JfNeTIJZG9xnPYPAv869iawc2ETfaE="',
        'aarch64-darwin = "sha256-BbJ1hqXX2EEFaQ7MzH7bv0i8PW1Xd0XLYfFjupkK308="',
    ):
        if terraform_pin not in flake:
            error(f"Nix Terraform release contract omits: {terraform_pin}")

    apply_workflow = (ROOT / ".github/workflows/apply.yml").read_text(
        "utf-8", errors="ignore"
    )
    for apply_gate in (
        "environment: plan",
        "ACTUAL_REF: ${{ github.ref }}",
        '"refs/heads/main"',
        "ref: ${{ github.sha }}",
    ):
        if apply_gate not in apply_workflow:
            error(f"apply workflow lacks exact-main/plan-identity gate: {apply_gate}")
    drift_workflow = (ROOT / ".github/workflows/drift.yml").read_text(
        "utf-8", errors="ignore"
    )
    if "tail -c 45000 artifacts/drift.txt" in drift_workflow:
        error("drift workflow publishes sensitive raw plan output into issues")
    stateful_plan_paths = {
        "scripts/terragrunt-scope.py": (ROOT / "scripts/terragrunt-scope.py").read_text(
            "utf-8", errors="ignore"
        ),
        "scripts/plan-changed.py": (ROOT / "scripts/plan-changed.py").read_text(
            "utf-8", errors="ignore"
        ),
        ".github/workflows/drift.yml": drift_workflow,
    }
    for path, text in stateful_plan_paths.items():
        if "-lock=false" in text:
            error(f"{path} disables Terraform state locking during plan")
        if "-lock-timeout=20m" not in text:
            error(f"{path} lacks the bounded Terraform state-lock timeout")

    for required_doc in (
        "docs/production-activation-gates.md",
        "docs/supply-chain-signer-contract.md",
        "docs/runbooks/binauthz-blocked-deploy.md",
        "docs/runbooks/gke-reconstruction.md",
        "docs/runbooks/state-lock-stuck.md",
        "docs/runbooks/vpc-sc-denial.md",
    ):
        if not (ROOT / required_doc).is_file():
            error(f"missing production operations document: {required_doc}")
    activation_gates = (ROOT / "docs/production-activation-gates.md").read_text(
        "utf-8", errors="ignore"
    )
    for ha_gate in (
        "standard profile",
        "node_locations",
        "total minimum of at least three",
        "topology-spread",
    ):
        if ha_gate not in activation_gates:
            error(f"Argo CD HA activation gate omits: {ha_gate}")

if ERRORS:
    for msg in sorted(set(ERRORS)):
        print(f"ERROR: {msg}", file=sys.stderr)
    print(f"{len(set(ERRORS))} production contract violation(s)", file=sys.stderr)
    raise SystemExit(1)
print(f"{REPOSITORY}: production contract passed")
