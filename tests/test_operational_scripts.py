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
                f"mindclade/.github/.github/workflows/{workflow}@refs/tags/v4.0.0"
            ),
        }
    return result


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

    def test_unit_traversal_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SCOPE.validate_unit(
                "development", "../outside", SCOPE.SCOPES["development"]
            )

    def test_customer_id_must_be_explicit_and_well_formed(self) -> None:
        with self.assertRaises(ValueError):
            ACCOUNT.validated_customer_id("")
        self.assertEqual(ACCOUNT.validated_customer_id("C01234567"), "C01234567")

    def test_retired_buildkite_contract_requires_null_resources(self) -> None:
        self.assertIsNone(
            ACCOUNT.validated_retired_buildkite(
                {
                    "enabled": False,
                    "workload_identity_pool": None,
                    "workload_identity_provider": None,
                }
            )
        )
        with self.assertRaises(ValueError):
            ACCOUNT.validated_retired_buildkite(
                {
                    "enabled": True,
                    "workload_identity_pool": "projects/123456789/locations/global/workloadIdentityPools/buildkite",
                    "workload_identity_provider": "projects/123456789/locations/global/workloadIdentityPools/buildkite/providers/buildkite",
                }
            )

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
        os.environ["ARTIFACT_RELEASE_IDENTITIES_JSON"] = json.dumps(
            release_identities(), sort_keys=True, separators=(",", ":")
        )

    def tearDown(self) -> None:
        if self.previous is None:
            os.environ.pop("ARTIFACT_RELEASE_IDENTITIES_JSON", None)
        else:
            os.environ["ARTIFACT_RELEASE_IDENTITIES_JSON"] = self.previous

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
            )
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
        return automation, gitops, binauthz

    def test_compiles_only_exact_applied_values(self) -> None:
        automation, gitops, binauthz = self.fixtures()
        contract = HANDOFF.compile_contract(automation, gitops, binauthz, "a" * 40)
        self.assertEqual(contract["environment"], "production")
        self.assertEqual(
            contract["variables"]["BINAUTHZ_DEPLOYMENT_ATTESTOR"],
            "deployment-attestor",
        )
        self.assertEqual(len(contract["variables"]), 16)
        self.assertEqual(contract["contract_version"], "1.1.0")
        self.assertFalse(contract["credential_material_included"])

    def test_sensitive_output_is_rejected(self) -> None:
        automation, gitops, binauthz = self.fixtures()
        binauthz["project_id"]["sensitive"] = True
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(automation, gitops, binauthz, "a" * 40)

    def test_mock_and_wrong_environment_outputs_are_rejected(self) -> None:
        automation, gitops, binauthz = self.fixtures()
        binauthz["project_id"]["value"] = "mock-production-platform"
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(automation, gitops, binauthz, "a" * 40)
        automation, gitops, binauthz = self.fixtures()
        binauthz["enforcement_mode"]["value"] = "DRYRUN_AUDIT_LOG_ONLY"
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(automation, gitops, binauthz, "a" * 40)
        automation, gitops, binauthz = self.fixtures()
        binauthz["project_id"]["value"] = "mc-staging-platform"
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(automation, gitops, binauthz, "a" * 40)

    def test_identity_names_and_project_trust_domains_are_exact(self) -> None:
        automation, gitops, binauthz = self.fixtures()
        automation["artifact_release_identity_contract"]["value"]["signer"][
            "service_account"
        ] = "sa-artifact-builder@mc-common-ci.iam.gserviceaccount.com"
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(automation, gitops, binauthz, "a" * 40)
        automation, gitops, binauthz = self.fixtures()
        gitops["github_config_identity_handoff"]["value"]["SA_GITOPS_RENDER"] = (
            "sa-gitops-render@mc-production-platform.iam.gserviceaccount.com"
        )
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(automation, gitops, binauthz, "a" * 40)

    def test_mutable_key_and_bootstrap_identity_drift_are_rejected(self) -> None:
        automation, gitops, binauthz = self.fixtures()
        binauthz["attestor_key_versions"]["value"]["deployment-attestor"] = (
            "projects/mc-common-security/locations/us/keyRings/r/cryptoKeys/k"
        )
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(automation, gitops, binauthz, "a" * 40)
        automation, gitops, binauthz = self.fixtures()
        binauthz["attestor_key_versions"]["value"]["deployment-attestor"] = (
            "projects/mc-common-security/locations/us/keyRings/r/cryptoKeys/"
            "attestor-build-attestor/cryptoKeyVersions/1"
        )
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(automation, gitops, binauthz, "a" * 40)
        automation, gitops, binauthz = self.fixtures()
        automation["artifact_release_identity_contract"]["value"]["signer"][
            "job_workflow_ref"
        ] = "mindclade/.github/.github/workflows/reusable-binauthz-sign.yml@main"
        with self.assertRaises(ValueError):
            HANDOFF.compile_contract(automation, gitops, binauthz, "a" * 40)

    def test_write_is_private_outside_repo_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "handoff.json"
            HANDOFF.write_contract(target, {"contract_version": "test"})
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                HANDOFF.write_contract(target, {"contract_version": "replacement"})


if __name__ == "__main__":
    unittest.main()
