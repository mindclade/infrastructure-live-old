#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Safety tests for infrastructure planning operators."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHANGED = load("plan_changed", "scripts/plan-changed.py")
SCOPE = load("terragrunt_scope", "scripts/terragrunt-scope.py")
ACCOUNT = load("bootstrap_account", "scripts/bootstrap-account.py")
ACCOUNT_VALIDATOR = load("validate_account", "scripts/validate-account.py")
STATE_PREFIX = load("classify_state_prefix", "scripts/classify-state-prefix.py")
HANDOFF = load(
    "export_applied_control_plane_handoff",
    "scripts/export-applied-control-plane-handoff.py",
)
MODULE_INTERFACES = load(
    "validate_module_interfaces", "scripts/validate-module-interfaces.py"
)


def release_identities(
    pool: str = "projects/123456789/locations/global/workloadIdentityPools/github",
) -> dict[str, dict[str, str]]:
    workflows = {
        "canary": "reusable-arc-wif-canary.yml",
        "builder": "reusable-arc-oci-build.yml",
        "qualification-reader": "reusable-arc-oci-qualify.yml",
        "qualifier": "reusable-arc-qualification-attest.yml",
        "signer": "reusable-binauthz-sign.yml",
        "promoter": "reusable-gitops-promote.yml",
    }
    result = {}
    for capability, workflow in workflows.items():
        subject = (
            "repo:mindclade@316676129/mindclade-internal-monorepo@1333792222:"
            + (
                "environment:release"
                if capability in {"signer", "promoter"}
                else "ref:refs/heads/main"
            )
        )
        provider = (
            "gh-mindclade-internal-monorepo"
            if capability == "signer"
            else f"gh-arc-{capability}"
        )
        mapped_subject = subject if capability == "signer" else f"arc-{capability}:{subject}"
        result[capability] = {
            "workload_identity_provider": f"{pool}/providers/{provider}",
            "principal": f"principal://iam.googleapis.com/{pool}/subject/{mapped_subject}",
            "subject": subject,
            "workflow_ref": "mindclade/mindclade-internal-monorepo/.github/workflows/release.yml@refs/heads/main",
            "job_workflow_ref": (
                f"mindclade/.github/.github/workflows/{workflow}@refs/tags/v5.0.0"
            ),
        }
    return result


def dr_evidence_identity(
    pool: str = "projects/123456789/locations/global/workloadIdentityPools/github",
) -> dict[str, object]:
    principals = {}
    for repository in (
        "bootstrap",
        "github-config",
        "infrastructure-live",
        "gitops",
    ):
        for environment in ("scratch", "staging"):
            key = f"{repository}:{environment}"
            principals[key] = (
                f"principal://iam.googleapis.com/{pool}/subject/dr-evidence:"
                f"repo:mindclade@316676129/{repository}@1333792222:"
                f"environment:{environment}"
            )
    return {
        "workload_identity_provider": f"{pool}/providers/gh-dr-evidence",
        "job_workflow_ref": (
            "mindclade/.github/.github/workflows/"
            "reusable-dr-evidence.yml@refs/tags/v5.0.0"
        ),
        "principals": principals,
    }


def production_qualification_identity(
    pool: str = "projects/123456789/locations/global/workloadIdentityPools/github",
) -> dict[str, str]:
    subject = (
        "repo:mindclade@316676129/gitops@1333792222:environment:production"
    )
    return {
        "workload_identity_provider": f"{pool}/providers/gh-production-qualification",
        "principal": (
            f"principal://iam.googleapis.com/{pool}/subject/"
            f"production-qualification:{subject}"
        ),
        "subject": subject,
        "workflow_ref": (
            "mindclade/gitops/.github/workflows/"
            "production-qualification-evidence.yml@refs/heads/main"
        ),
    }


def workstation_image_identity(
    pool: str = "projects/123456789/locations/global/workloadIdentityPools/github",
) -> dict[str, str]:
    subject = (
        "repo:mindclade@316676129/mindclade-internal-monorepo@1333792222:"
        "environment:workstation-image-publication"
    )
    return {
        "workload_identity_provider": f"{pool}/providers/gh-workstation-image",
        "principal": (
            f"principal://iam.googleapis.com/{pool}/subject/workstation-image:{subject}"
        ),
        "repository": "mindclade/mindclade-internal-monorepo",
        "repository_id": "1333792222",
        "subject": subject,
        "workflow_ref": (
            "mindclade/mindclade-internal-monorepo/.github/workflows/"
            "nixos-image.yml@refs/heads/main"
        ),
        "job_workflow_ref": (
            "mindclade/.github/.github/workflows/"
            "reusable-nixos-gce-image-publish.yml@refs/tags/v5.0.0"
        ),
    }


def bazel_cache_identity(
    pool: str = "projects/123456789/locations/global/workloadIdentityPools/github",
) -> dict[str, Any]:
    repository = "mindclade/mindclade-internal-monorepo"
    route_specs = {
        "pull-request-read": (
            "read",
            "pull_request",
            "pull-request-merge",
            f"{repository}/.github/workflows/presubmit.yml",
        ),
        "trusted-main-write": (
            "write",
            "push",
            "protected-main",
            f"{repository}/.github/workflows/presubmit.yml",
        ),
        "merge-group-write": (
            "write",
            "merge_group",
            "protected-merge-queue",
            f"{repository}/.github/workflows/presubmit.yml",
        ),
        "nightly-write": (
            "write",
            "schedule",
            "protected-main",
            f"{repository}/.github/workflows/nightly.yml",
        ),
    }
    return {
        "workload_identity_provider": f"{pool}/providers/gh-bazel-cache",
        "repository": repository,
        "repository_owner_id": "316676129",
        "repository_id": "1333792222",
        "routes": {
            route: {
                "access": access,
                "event_name": event_name,
                "principal": (
                    f"principal://iam.googleapis.com/{pool}/subject/"
                    f"bazel-cache:{route}"
                ),
                "ref_policy": ref_policy,
                "workflow_path": workflow_path,
            }
            for route, (
                access,
                event_name,
                ref_policy,
                workflow_path,
            ) in route_specs.items()
        },
    }


class PlanSafetyTest(unittest.TestCase):
    def test_repository_root_is_never_a_plan_directory(self) -> None:
        with self.assertRaises(ValueError):
            SCOPE.validated_plan_path(ROOT)

    def test_temporary_child_is_an_allowed_plan_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "plans" / "development"
            self.assertEqual(SCOPE.validated_plan_path(candidate), candidate.resolve())

    def test_checksum_manifest_detects_tampering_and_extra_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "plan.tfplan").write_text("first", encoding="utf-8")
            SCOPE.write_checksums(bundle)
            SCOPE.verify_checksums(bundle)
            (bundle / "plan.tfplan").write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                SCOPE.verify_checksums(bundle)

    def test_dependent_closure_is_order_independent(self) -> None:
        selected = {Path("a")}
        dependencies = {Path("c"): {Path("b")}, Path("b"): {Path("a")}}
        CHANGED.dependent_closure(selected, dependencies)
        self.assertEqual(selected, {Path("a"), Path("b"), Path("c")})

    def test_pr_impact_separates_direct_and_transitive_units(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "impact.json"
            CHANGED.write_impact(
                output,
                "origin/main",
                {Path("3-networks/staging/vpc")},
                {
                    Path("3-networks/staging/vpc"),
                    Path("5-workloads/staging/gke"),
                },
            )
            impact = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(impact["summary"]["dependentUnitCount"], 1)
        self.assertTrue(impact["reviewFlags"]["network"])
        self.assertFalse(impact["reviewFlags"]["production"])

    def test_unit_traversal_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SCOPE.validate_unit(
                "development", "../outside", SCOPE.SCOPES["development"]
            )

    def test_customer_id_must_be_explicit_and_well_formed(self) -> None:
        with self.assertRaises(ValueError):
            ACCOUNT.validated_customer_id("")
        self.assertEqual(ACCOUNT.validated_customer_id("C01234567"), "C01234567")

    def test_release_identity_contract_is_capability_exact(self) -> None:
        pool = "projects/123456789/locations/global/workloadIdentityPools/github"
        identities = release_identities(pool)
        self.assertEqual(
            ACCOUNT.validated_release_identities(identities, pool, "mindclade"),
            identities,
        )
        self.assertEqual(
            ACCOUNT_VALIDATOR.release_identity_errors(
                json.dumps(identities), pool, "mindclade"
            ),
            [],
        )
        identities["builder"]["principal"] = identities["qualifier"]["principal"]
        with self.assertRaisesRegex(ValueError, "builder has wrong principal"):
            ACCOUNT.validated_release_identities(identities, pool, "mindclade")
        self.assertTrue(
            ACCOUNT_VALIDATOR.release_identity_errors(
                json.dumps(identities), pool, "mindclade"
            )
        )

    def test_dr_evidence_identity_contract_is_caller_exact(self) -> None:
        pool = "projects/123456789/locations/global/workloadIdentityPools/github"
        identity = dr_evidence_identity(pool)
        self.assertEqual(
            ACCOUNT.validated_dr_evidence_identity(identity, pool, "mindclade"),
            identity,
        )
        self.assertEqual(
            ACCOUNT_VALIDATOR.dr_evidence_identity_errors(
                json.dumps(identity), pool, "mindclade"
            ),
            [],
        )
        identity["principals"]["gitops:staging"] = identity["principals"][
            "bootstrap:staging"
        ]
        with self.assertRaisesRegex(ValueError, "gitops:staging"):
            ACCOUNT.validated_dr_evidence_identity(identity, pool, "mindclade")
        self.assertTrue(
            ACCOUNT_VALIDATOR.dr_evidence_identity_errors(
                json.dumps(identity), pool, "mindclade"
            )
        )

    def test_bazel_cache_identity_contract_is_route_exact(self) -> None:
        pool = "projects/123456789/locations/global/workloadIdentityPools/github"
        identity = bazel_cache_identity(pool)
        self.assertEqual(
            ACCOUNT.validated_bazel_cache_identity(identity, pool, "mindclade"),
            identity,
        )
        self.assertEqual(
            ACCOUNT_VALIDATOR.bazel_cache_identity_errors(
                json.dumps(identity), pool, "mindclade"
            ),
            [],
        )

    def test_bazel_cache_identity_rejects_read_escalation_and_stale_routes(
        self,
    ) -> None:
        pool = "projects/123456789/locations/global/workloadIdentityPools/github"
        escalated = bazel_cache_identity(pool)
        escalated["routes"]["pull-request-read"]["access"] = "write"
        with self.assertRaisesRegex(ValueError, "pull-request-read"):
            ACCOUNT.validated_bazel_cache_identity(escalated, pool, "mindclade")
        self.assertTrue(
            ACCOUNT_VALIDATOR.bazel_cache_identity_errors(
                json.dumps(escalated), pool, "mindclade"
            )
        )

        stale = bazel_cache_identity(pool)
        stale["routes"]["manual-write"] = stale["routes"]["nightly-write"]
        with self.assertRaisesRegex(ValueError, "inventory is not exact"):
            ACCOUNT.validated_bazel_cache_identity(stale, pool, "mindclade")
        self.assertIn(
            "Bazel cache identity route inventory is not exact",
            ACCOUNT_VALIDATOR.bazel_cache_identity_errors(
                json.dumps(stale), pool, "mindclade"
            ),
        )

    def test_state_prefix_accepts_only_exact_no_object_result(self) -> None:
        self.assertEqual(STATE_PREFIX.classify(0, ""), "existing-or-empty")
        self.assertEqual(
            STATE_PREFIX.classify(1, f"{STATE_PREFIX.NO_OBJECTS}\n"), "fresh"
        )
        for status, stderr in (
            (1, "ERROR: permission denied\n"),
            (1, f"warning\n{STATE_PREFIX.NO_OBJECTS}\n"),
            (2, f"{STATE_PREFIX.NO_OBJECTS}\n"),
            (0, "warning\n"),
        ):
            with self.subTest(status=status, stderr=stderr):
                with self.assertRaises(ValueError):
                    STATE_PREFIX.classify(status, stderr)


class ImportRuntimeContractTest(unittest.TestCase):
    def test_module_interface_contract_distinguishes_required_variables(self) -> None:
        declared, required = MODULE_INTERFACES.variable_contract(
            '''
            variable "required_string" {
              type = string
            }
            variable "optional_null" {
              type    = string
              default = null
            }
            variable "optional_object" {
              type = object({
                enabled = bool
              })
              default = {
                enabled = false
              }
            }
            '''
        )
        self.assertEqual(
            declared, {"required_string", "optional_null", "optional_object"}
        )
        self.assertEqual(required, {"required_string"})

    def test_candidate_module_policy_requires_one_matching_planned_version(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            policy = repo / "infra/terraform/governance/version.toml"
            policy.parent.mkdir(parents=True)
            policy.write_text(
                'contract_version = "0.4.0"\nstatus = "planned"\n',
                encoding="utf-8",
            )

            MODULE_INTERFACES.validate_candidate_version(repo, "v0.4.0")
            with self.assertRaisesRegex(RuntimeError, "planned contract version"):
                MODULE_INTERFACES.validate_candidate_version(repo, "v0.4.1")

            policy.write_text(
                'contract_version = "0.4.0"\nstatus = "released"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "planned contract version"):
                MODULE_INTERFACES.validate_candidate_version(repo, "v0.4.0")

    def test_candidate_module_is_read_only_from_the_planned_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            module = repo / "infra/terraform/modules/example"
            module.mkdir(parents=True)
            (module / "variables.tf").write_text(
                'variable "required" { type = string }\n', encoding="utf-8"
            )

            source = MODULE_INTERFACES.module_tf(
                repo, "v0.4.0", "example", "v0.4.0"
            )
            self.assertIn('variable "required"', source)

    def test_candidate_policy_rejects_duplicate_control_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            policy = repo / "infra/terraform/governance/version.toml"
            policy.parent.mkdir(parents=True)
            policy.write_text(
                'contract_version = "0.4.0"\n'
                'contract_version = "0.4.1"\n'
                'status = "planned"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "exactly one string"):
                MODULE_INTERFACES.validate_candidate_version(repo, "v0.4.0")

    def test_every_provider_lock_uses_terraform_115_normalized_constraints(
        self,
    ) -> None:
        locks = sorted(ROOT.rglob(".terraform.lock.hcl"))
        unit_directories = {
            path.parent
            for path in ROOT.rglob("terragrunt.hcl")
            if not any(part in {".terraform", ".terragrunt-cache"} for part in path.parts)
        }
        self.assertEqual({lock.parent for lock in locks}, unit_directories | {ROOT})
        for lock in locks:
            text = lock.read_text(encoding="utf-8")
            self.assertEqual(text.count('constraints = "7.41.0"'), 2, lock)
            self.assertEqual(text.count('"h1:'), 4, lock)
            self.assertNotIn('constraints = "= 7.41.0"', text, lock)

    def test_both_nix_shells_pin_terragrunt_to_terraform(self) -> None:
        flake = (ROOT / "flake.nix").read_text(encoding="utf-8")
        self.assertEqual(
            flake.count('TG_TF_PATH = "${terraformPinned}/bin/terraform";'), 2
        )

    def test_baseline_only_skips_the_folders_state_dependency(self) -> None:
        policy = (ROOT / "1-org/org-policies/terragrunt.hcl").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'baseline_org_policy_adoption = get_env("ORG_POLICY_ACTIVATION_PHASE", "") == "baseline"',
            policy,
        )
        self.assertIn("skip_outputs = local.baseline_org_policy_adoption", policy)
        self.assertIn("mock_outputs = local.baseline_org_policy_adoption ? {", policy)
        self.assertNotIn("skip_outputs = true", policy)

    def test_baseline_mock_commands_are_minimal_and_support_plan_rendering(
        self,
    ) -> None:
        policy = (ROOT / "1-org/org-policies/terragrunt.hcl").read_text(
            encoding="utf-8"
        )
        match = re.search(
            r"mock_outputs_allowed_terraform_commands\s*=\s*"
            r"local\.baseline_org_policy_adoption\s*\?\s*\[(.*?)\]\s*:\s*\[\]",
            policy,
            re.S,
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(
            set(re.findall(r'"([a-z-]+)"', match.group(1))),
            {"import", "init", "plan", "show", "validate"},
        )

    def test_domain_restricted_sharing_requires_one_exact_customer_id(self) -> None:
        variables = (ROOT / "1-org/org-policies/module/variables.tf").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'length(var.list_policies["iam.allowedPolicyMemberDomains"].allowed_values) == 1',
            variables,
        )
        self.assertIn(
            'var.list_policies["iam.allowedPolicyMemberDomains"].allowed_values[0] == var.cloud_identity_customer_id',
            variables,
        )
        self.assertIn(
            'length(var.list_policies["iam.allowedPolicyMemberDomains"].denied_values) == 0',
            variables,
        )
        self.assertNotIn(
            "allowed_values == [var.cloud_identity_customer_id]", variables
        )

    def test_import_runbook_has_fail_closed_resume_path(self) -> None:
        runbook = (ROOT / "docs/initial-import.md").read_text(encoding="utf-8")
        for required in (
            "Resume after a completed import",
            "resume_verified_import",
            "must not be imported again",
            "state generation changed after the stopped import",
            'terragrunt show -json > "${state_json}"',
            'previous_generation="${current_generation}"',
        ):
            self.assertIn(required, runbook)


class AppliedControlPlaneHandoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous = os.environ.get("ARTIFACT_RELEASE_IDENTITIES_JSON")
        self.previous_qualification = os.environ.get(
            "PRODUCTION_QUALIFICATION_IDENTITY_JSON"
        )
        self.previous_bazel_cache = os.environ.get("BAZEL_CACHE_IDENTITY_JSON")
        self.previous_workstation_image = os.environ.get(
            "WORKSTATION_IMAGE_IDENTITY_JSON"
        )
        os.environ["ARTIFACT_RELEASE_IDENTITIES_JSON"] = json.dumps(
            release_identities(), sort_keys=True, separators=(",", ":")
        )
        os.environ["PRODUCTION_QUALIFICATION_IDENTITY_JSON"] = json.dumps(
            production_qualification_identity(),
            sort_keys=True,
            separators=(",", ":"),
        )
        os.environ["BAZEL_CACHE_IDENTITY_JSON"] = json.dumps(
            bazel_cache_identity(), sort_keys=True, separators=(",", ":")
        )
        os.environ["WORKSTATION_IMAGE_IDENTITY_JSON"] = json.dumps(
            workstation_image_identity(), sort_keys=True, separators=(",", ":")
        )

    def tearDown(self) -> None:
        if self.previous is None:
            os.environ.pop("ARTIFACT_RELEASE_IDENTITIES_JSON", None)
        else:
            os.environ["ARTIFACT_RELEASE_IDENTITIES_JSON"] = self.previous
        if self.previous_qualification is None:
            os.environ.pop("PRODUCTION_QUALIFICATION_IDENTITY_JSON", None)
        else:
            os.environ["PRODUCTION_QUALIFICATION_IDENTITY_JSON"] = (
                self.previous_qualification
            )
        if self.previous_bazel_cache is None:
            os.environ.pop("BAZEL_CACHE_IDENTITY_JSON", None)
        else:
            os.environ["BAZEL_CACHE_IDENTITY_JSON"] = self.previous_bazel_cache
        if self.previous_workstation_image is None:
            os.environ.pop("WORKSTATION_IMAGE_IDENTITY_JSON", None)
        else:
            os.environ["WORKSTATION_IMAGE_IDENTITY_JSON"] = (
                self.previous_workstation_image
            )

    @staticmethod
    def output(value, sensitive: bool = False):
        return {"sensitive": sensitive, "type": "dynamic", "value": value}

    def fixtures(self):
        accounts = {
            "canary": "sa-arc-canary",
            "builder": "sa-artifact-builder",
            "qualification-reader": "sa-artifact-qual-reader",
            "qualifier": "sa-artifact-qualifier",
            "signer": "sa-artifact-signer",
            "promoter": "sa-artifact-promoter",
        }
        applied_release_identities = {
            capability: {
                **identity,
                "service_account": (
                    f"{accounts[capability]}@mc-common-ci.iam.gserviceaccount.com"
                ),
            }
            for capability, identity in release_identities().items()
        }
        automation = {
            "artifact_release_identity_contract": self.output(
                applied_release_identities
            ),
            "ci_project_id": self.output("mc-common-ci"),
            "bazel_cache_identity_contract": self.output(
                {
                    "WIF_PROVIDER_BAZEL_CACHE": bazel_cache_identity()[
                        "workload_identity_provider"
                    ],
                    "SA_BAZEL_CACHE_READER": (
                        "bazel-cache-reader@mc-common-ci.iam.gserviceaccount.com"
                    ),
                    "SA_BAZEL_CACHE_WRITER": (
                        "bazel-cache-writer@mc-common-ci.iam.gserviceaccount.com"
                    ),
                    "repository": bazel_cache_identity()["repository"],
                    "repository_owner_id": bazel_cache_identity()[
                        "repository_owner_id"
                    ],
                    "repository_id": bazel_cache_identity()["repository_id"],
                    "routes": bazel_cache_identity()["routes"],
                }
            ),
            "workstation_image_identity_contract": self.output(
                {
                    "WIF_PROVIDER_WORKSTATION_IMAGE": workstation_image_identity()[
                        "workload_identity_provider"
                    ],
                    "SA_WORKSTATION_IMAGE_BUILDER": (
                        "workstation-image-pub@mc-common-ci.iam.gserviceaccount.com"
                    ),
                    "principal": workstation_image_identity()["principal"],
                    "repository": workstation_image_identity()["repository"],
                    "repository_id": workstation_image_identity()["repository_id"],
                    "subject": workstation_image_identity()["subject"],
                    "workflow_ref": workstation_image_identity()["workflow_ref"],
                    "job_workflow_ref": workstation_image_identity()["job_workflow_ref"],
                }
            ),
        }
        gitops = {
            "github_config_identity_handoff": self.output(
                {
                    "SA_GITOPS_RENDER": (
                        "sa-gitops-render@mc-common-security.iam.gserviceaccount.com"
                    ),
                    "SA_GITOPS_VERIFIER": (
                        "sa-gitops-verifier@mc-common-security.iam.gserviceaccount.com"
                    ),
                }
            ),
            "production_qualification_identity_handoff": self.output(
                {
                    "WIF_PROVIDER_PRODUCTION_QUALIFICATION": production_qualification_identity()[
                        "workload_identity_provider"
                    ],
                    "SA_PRODUCTION_QUALIFICATION_READER": (
                        "sa-prod-qual-reader@mc-common-security.iam.gserviceaccount.com"
                    ),
                    "SA_PRODUCTION_QUALIFICATION_EVALUATOR": (
                        "sa-prod-qual-evaluator@mc-common-security.iam.gserviceaccount.com"
                    ),
                    "SA_PRODUCTION_QUALIFICATION_WRITER": (
                        "sa-prod-qual-writer@mc-common-security.iam.gserviceaccount.com"
                    ),
                    "PRODUCTION_QUALIFICATION_PROJECT": "mc-common-security",
                    "PRODUCTION_QUALIFICATION_PRIVATE_KEY_SECRET": (
                        "github-app-production-qualification-reader-pem"
                    ),
                    "PRODUCTION_ELIGIBILITY_SIGNING_KEY_ID": (
                        "production-eligibility-v1"
                    ),
                    "PRODUCTION_ELIGIBILITY_KMS_KEY_VERSION": (
                        "projects/mc-common-security/locations/us-central1/keyRings/"
                        "mc-global/cryptoKeys/production-eligibility-decisions/"
                        "cryptoKeyVersions/1"
                    ),
                }
            ),
            "production_qualification_identity_contract": self.output(
                production_qualification_identity()
            ),
        }
        binauthz = {
            "project_id": self.output("mc-production-platform"),
            "attestor_names": self.output({name: name for name in HANDOFF.ATTESTORS}),
            "attestor_key_versions": self.output(
                {
                    "deployment-attestor": (
                        "projects/mc-common-security/locations/us-central1/keyRings/"
                        "binauthz/cryptoKeys/attestor-deployment-attestor/"
                        "cryptoKeyVersions/1"
                    )
                }
            ),
            "enforcement_mode": self.output("ENFORCED_BLOCK_AND_AUDIT_LOG"),
        }
        qualification = {
            "bucket": self.output(
                {
                    "id": "mc-production-qualification-evidence",
                    "name": "mc-production-qualification-evidence",
                    "self_link": "https://storage.invalid/bucket",
                    "url": "gs://mc-production-qualification-evidence",
                }
            )
        }
        workstation_source = {
            "bucket": self.output(
                {
                    "id": "mc-common-ci-workstation-images",
                    "name": "mc-common-ci-workstation-images",
                    "self_link": "https://storage.invalid/workstation-images",
                    "url": "gs://mc-common-ci-workstation-images",
                }
            )
        }
        return automation, gitops, binauthz, qualification, workstation_source

    def test_compiles_only_exact_applied_values(self) -> None:
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        contract = HANDOFF.compile_contract(
            automation, gitops, binauthz, qualification, workstation_source, "a" * 40
        )
        self.assertEqual(contract["environment"], "production")
        self.assertEqual(
            contract["variables"]["BINAUTHZ_DEPLOYMENT_ATTESTOR"],
            "deployment-attestor",
        )
        self.assertEqual(len(contract["variables"]), 31)
        self.assertEqual(contract["contract_version"], "1.5.0")
        self.assertEqual(
            contract["variables"]["SA_BAZEL_CACHE_READER"],
            "bazel-cache-reader@mc-common-ci.iam.gserviceaccount.com",
        )
        self.assertFalse(contract["credential_material_included"])

    def test_workstation_image_handoff_is_applied_and_exact(self) -> None:
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        contract = HANDOFF.compile_contract(
            automation, gitops, binauthz, qualification, workstation_source, "a" * 40
        )
        self.assertEqual(
            contract["variables"]["WIF_PROVIDER_WORKSTATION_IMAGE"],
            workstation_image_identity()["workload_identity_provider"],
        )
        self.assertEqual(
            contract["variables"]["WORKSTATION_IMAGE_BUCKET"],
            "mc-common-ci-workstation-images",
        )
        workstation_source["bucket"]["value"]["name"] = "unexpected-images"
        with self.assertRaisesRegex(ValueError, "bucket name is not exact"):
            HANDOFF.compile_contract(
                automation,
                gitops,
                binauthz,
                qualification,
                workstation_source,
                "a" * 40,
            )

    def test_bazel_cache_applied_output_must_match_bootstrap_and_role_split(self) -> None:
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        automation["bazel_cache_identity_contract"]["value"]["routes"][
            "pull-request-read"
        ]["access"] = "write"
        with self.assertRaisesRegex(ValueError, "differs from bootstrap"):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )

        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        automation["bazel_cache_identity_contract"]["value"][
            "SA_BAZEL_CACHE_WRITER"
        ] = "bazel-cache-reader@mc-common-ci.iam.gserviceaccount.com"
        with self.assertRaisesRegex(ValueError, "wrong service account"):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )

        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        os.environ["BAZEL_CACHE_IDENTITY_JSON"] = "{}"
        with self.assertRaisesRegex(ValueError, "field inventory"):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )

    def test_sensitive_output_is_rejected(self) -> None:
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        binauthz["project_id"]["sensitive"] = True
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )

    def test_mock_and_wrong_environment_outputs_are_rejected(self) -> None:
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        binauthz["project_id"]["value"] = "mock-production-platform"
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        binauthz["enforcement_mode"]["value"] = "DRYRUN_AUDIT_LOG_ONLY"
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        binauthz["project_id"]["value"] = "mc-staging-platform"
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )

    def test_identity_names_and_project_trust_domains_are_exact(self) -> None:
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        automation["artifact_release_identity_contract"]["value"]["signer"][
            "service_account"
        ] = "sa-artifact-builder@mc-common-ci.iam.gserviceaccount.com"
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        gitops["github_config_identity_handoff"]["value"]["SA_GITOPS_RENDER"] = (
            "sa-gitops-render@mc-production-platform.iam.gserviceaccount.com"
        )
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )

    def test_mutable_key_and_bootstrap_identity_drift_are_rejected(self) -> None:
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        binauthz["attestor_key_versions"]["value"]["deployment-attestor"] = (
            "projects/mc-common-security/locations/us/keyRings/r/cryptoKeys/k"
        )
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        binauthz["attestor_key_versions"]["value"]["deployment-attestor"] = (
            "projects/mc-common-security/locations/us/keyRings/r/cryptoKeys/"
            "attestor-build-attestor/cryptoKeyVersions/1"
        )
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        automation["artifact_release_identity_contract"]["value"]["signer"][
            "job_workflow_ref"
        ] = "mindclade/.github/.github/workflows/reusable-binauthz-sign.yml@main"
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )

    def test_qualification_identity_bucket_and_role_split_are_exact(self) -> None:
        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        gitops["production_qualification_identity_contract"]["value"][
            "subject"
        ] = "repo:mindclade@316676129/gitops@1333792222:environment:staging"
        with self.assertRaisesRegex(ValueError, "differs from bootstrap"):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )

        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        qualification["bucket"]["value"]["name"] = "unexpected-evidence"
        with self.assertRaisesRegex(ValueError, "bucket name is not exact"):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )

        automation, gitops, binauthz, qualification, workstation_source = self.fixtures()
        gitops["production_qualification_identity_handoff"]["value"][
            "SA_PRODUCTION_QUALIFICATION_WRITER"
        ] = "sa-prod-qual-reader@mc-common-security.iam.gserviceaccount.com"
        with self.assertRaisesRegex(ValueError, "wrong service account"):
            HANDOFF.compile_contract(
                automation, gitops, binauthz, qualification, workstation_source, "a" * 40
            )

    def test_write_is_private_outside_repo_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "handoff.json"
            HANDOFF.write_contract(target, {"contract_version": "test"})
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                HANDOFF.write_contract(target, {"contract_version": "replacement"})


if __name__ == "__main__":
    unittest.main()
