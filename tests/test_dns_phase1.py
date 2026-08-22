# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GOVERNANCE = load_script("dns_governance", "validate_dns_governance.py")
CUTOVER = load_script("dns_cutover", "generate_dns_cutover_packets.py")
RELEASE_CANDIDATE = load_script(
    "module_release_candidate", "validate-module-release-candidate.py"
)


class DNSPhaseOneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = GOVERNANCE.load_json(GOVERNANCE.DEFAULT_INVENTORY)
        self.evidence = GOVERNANCE.load_json(GOVERNANCE.DEFAULT_EVIDENCE)
        self.exceptions = GOVERNANCE.load_json(GOVERNANCE.DEFAULT_EXCEPTIONS)
        self.as_of = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)

    def test_current_contracts_are_valid_and_fail_closed(self) -> None:
        self.assertEqual(
            [], GOVERNANCE.validate_evidence_contract(self.evidence, self.inventory, self.as_of)
        )
        self.assertEqual(
            [],
            GOVERNANCE.validate_exception_contract(self.exceptions, self.inventory, self.as_of),
        )
        derived = GOVERNANCE.derive_readiness(
            self.inventory, self.evidence, self.exceptions, self.as_of
        )
        self.assertTrue(derived)
        self.assertTrue(all(not state["inventory_complete"] for state in derived.values()))
        self.assertTrue(all(not state["delegation_ready"] for state in derived.values()))

    def test_local_evidence_uri_is_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        gate = next(
            gate
            for gate in evidence["domains"][0]["gates"]
            if gate["gate_id"] == "workspace_identity_audit"
        )
        gate["uri"] = "file:///private/tmp/workspace-audit.md"
        errors = GOVERNANCE.validate_evidence_contract(evidence, self.inventory, self.as_of)
        self.assertTrue(any("temporary evidence" in error for error in errors))

    def test_approval_without_generation_and_reviewer_is_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        gate = next(
            gate
            for gate in evidence["domains"][0]["gates"]
            if gate["gate_id"] == "workspace_identity_audit"
        )
        gate["status"] = "approved"
        errors = GOVERNANCE.validate_evidence_contract(evidence, self.inventory, self.as_of)
        self.assertTrue(any("generation" in error for error in errors))
        self.assertTrue(any("reviewer" in error for error in errors))

    def test_required_gate_sets_are_exact_and_phase_owned(self) -> None:
        missing = copy.deepcopy(self.evidence)
        missing["domains"][0]["gates"] = [
            gate
            for gate in missing["domains"][0]["gates"]
            if gate["gate_id"] != "dnssec_preflight"
        ]
        errors = GOVERNANCE.validate_evidence_contract(missing, self.inventory, self.as_of)
        self.assertTrue(any("missing=['dnssec_preflight']" in error for error in errors))

        additional = copy.deepcopy(self.evidence)
        additional["portfolio_gates"].append(
            {"gate_id": "bypass", "phase": "delegation", "status": "pending"}
        )
        errors = GOVERNANCE.validate_evidence_contract(additional, self.inventory, self.as_of)
        self.assertTrue(any("unexpected=['bypass']" in error for error in errors))

        rephased = copy.deepcopy(self.evidence)
        rephased["portfolio_gates"][0]["phase"] = "delegation"
        errors = GOVERNANCE.validate_evidence_contract(rephased, self.inventory, self.as_of)
        self.assertTrue(any("phase must be inventory" in error for error in errors))

    def test_evidence_and_exception_timestamps_are_ordered(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        gate = next(
            gate
            for gate in evidence["domains"][0]["gates"]
            if gate["gate_id"] == "workspace_identity_audit"
        )
        gate.update(
            {
                "status": "approved",
                "uri": "gs://mc-common-dns-change-evidence/dns/test.json#1",
                "observed_at": "2026-08-22T10:00:00Z",
                "sha256": "0" * 64,
                "reviewer": "reviewer@mindclade.com",
                "reviewed_at": "2026-08-22T09:00:00Z",
                "expires_at": "2026-08-22T08:00:00Z",
            }
        )
        errors = GOVERNANCE.validate_evidence_contract(evidence, self.inventory, self.as_of)
        self.assertTrue(any("reviewed_at must not precede observed_at" in error for error in errors))
        self.assertTrue(any("expires_at must be later than reviewed_at" in error for error in errors))

        exceptions = copy.deepcopy(self.exceptions)
        exception = exceptions["domains"][0]["exceptions"][0]
        exception.update(
            {
                "review_status": "approved",
                "change_record": "CHG-future",
                "approved_by": "reviewer@mindclade.com",
                "approved_at": "2026-08-23T00:00:00Z",
                "expires_at": "2026-08-22T23:00:00Z",
            }
        )
        errors = GOVERNANCE.validate_exception_contract(exceptions, self.inventory, self.as_of)
        self.assertTrue(any("evaluation time" in error for error in errors))
        self.assertTrue(any("expires_at must be later than approved_at" in error for error in errors))

    def test_expired_public_record_exception_is_rejected(self) -> None:
        exceptions = copy.deepcopy(self.exceptions)
        exception = exceptions["domains"][0]["exceptions"][0]
        exception.update(
            {
                "review_status": "approved",
                "change_record": "CHG-test",
                "approved_by": "reviewer@mindclade.com",
                "approved_at": "2026-01-01T00:00:00Z",
                "expires_at": "2026-02-01T00:00:00Z",
            }
        )
        errors = GOVERNANCE.validate_exception_contract(exceptions, self.inventory, self.as_of)
        self.assertTrue(any("expired" in error for error in errors))

    def test_cutover_packets_are_deterministic_and_write_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incumbent = root / "incumbent"
            target = root / "target"
            incumbent.mkdir()
            target.mkdir()
            domains = sorted(GOVERNANCE.domain_map(self.inventory, "inventory", []))
            for domain in domains:
                before = {
                    "schema_version": 1,
                    "domain": domain,
                    "captured_at": "2026-08-20T00:00:00Z",
                    "authoritative_nameservers": [f"old-ns.{domain}."],
                    "parent_ds": [],
                    "records": [{"key": "before", "type": "TXT", "values": ["full"]}],
                }
                after = {
                    "schema_version": 1,
                    "domain": domain,
                    "captured_at": "2026-08-21T00:00:00Z",
                    "authoritative_nameservers": [f"new-ns.{domain}."],
                    "parent_ds": ["12345 13 2 abcdef"],
                    "records": [{"key": "after", "type": "TXT", "values": ["full"]}],
                }
                (incumbent / f"{domain}.json").write_text(
                    json.dumps(before, sort_keys=True) + "\n", encoding="utf-8"
                )
                (target / f"{domain}.json").write_text(
                    json.dumps(after, sort_keys=True) + "\n", encoding="utf-8"
                )
            arguments = {
                "inventory": self.inventory,
                "evidence": self.evidence,
                "exceptions": self.exceptions,
                "evidence_path": GOVERNANCE.DEFAULT_EVIDENCE,
                "incumbent_dir": incumbent,
                "target_dir": target,
                "domains": domains,
                "generated_at": "2026-08-22T12:00:00Z",
                "change_id": "CHG-test",
                "window_start": "2026-08-25T12:00:00Z",
                "window_end": "2026-08-25T13:00:00Z",
                "ttl_lowered_at": "2026-08-22T12:00:00Z",
            }
            first = CUTOVER.build_packets(**arguments)
            second = CUTOVER.build_packets(**arguments)
            self.assertEqual(first, second)
            sample = first[domains[0]]
            self.assertEqual(
                "before", sample["incumbent_snapshot"]["content"]["records"][0]["key"]
            )
            self.assertEqual(
                "after", sample["target_snapshot"]["content"]["records"][0]["key"]
            )
            self.assertFalse(sample["incumbent_snapshot"]["evidence_binding"]["matches"])
            self.assertFalse(sample["target_snapshot"]["evidence_binding"]["matches"])
            self.assertEqual(
                CUTOVER.canonical_sha256(sample["incumbent_snapshot"]["content"]),
                sample["incumbent_snapshot"]["sha256"],
            )
            self.assertEqual(
                CUTOVER.canonical_sha256(sample["target_snapshot"]["content"]),
                sample["target_snapshot"]["sha256"],
            )
            self.assertTrue(all(isinstance(argv, list) for argv in sample["preflight_argv"]))
            self.assertTrue(all(argv[0] == "dig" for argv in sample["preflight_argv"]))
            self.assertIn(["dig", "+trace", "+dnssec", "NS", "ai."], sample["preflight_argv"])
            self.assertNotIn("a.gtld-servers.net", json.dumps(sample["preflight_argv"]))
            output = root / "packets"
            CUTOVER.write_packets(first, output)
            with self.assertRaises(FileExistsError):
                CUTOVER.write_packets(first, output)

            with self.assertRaisesRegex(ValueError, "ttl_lowered_at"):
                CUTOVER.build_packets(
                    **{**arguments, "ttl_lowered_at": "2026-08-23T12:00:00Z"}
                )
            with self.assertRaisesRegex(ValueError, "generated_at"):
                CUTOVER.build_packets(
                    **{
                        **arguments,
                        "ttl_lowered_at": "2026-08-18T12:00:00Z",
                        "window_start": "2026-08-21T12:00:00Z",
                        "window_end": "2026-08-21T13:00:00Z",
                    }
                )

            split_brain_evidence = copy.deepcopy(self.evidence)
            split_brain_evidence["evidence_store"]["retention_mode"] = "governance"
            with self.assertRaisesRegex(ValueError, "exactly match the evidence file"):
                CUTOVER.build_packets(**{**arguments, "evidence": split_brain_evidence})

            unsafe_path = incumbent / f"{domains[0]}.json"
            unsafe = json.loads(unsafe_path.read_text(encoding="utf-8"))
            unsafe["authoritative_nameservers"] = ["ns.example.;touch.invalid"]
            unsafe_path.write_text(json.dumps(unsafe) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "valid DNS name"):
                CUTOVER.build_packets(**arguments)

            unsafe["authoritative_nameservers"] = [f"old-ns.{domains[0]}."]
            unsafe["captured_at"] = "2026-08-23T00:00:00Z"
            unsafe_path.write_text(json.dumps(unsafe) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "captured after generated_at"):
                CUTOVER.build_packets(**arguments)

    def test_approved_snapshot_digest_must_match(self) -> None:
        evidence_entry = copy.deepcopy(self.evidence["domains"][0])
        gate = next(
            gate
            for gate in evidence_entry["gates"]
            if gate["gate_id"] == "incumbent_zone_snapshot"
        )
        captured = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
        gate.update(
            {
                "status": "approved",
                "sha256": "0" * 64,
                "observed_at": "2026-08-22T12:00:00Z",
            }
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            CUTOVER.snapshot_evidence_binding(
                evidence_entry, "incumbent_zone_snapshot", "1" * 64, captured
            )
        binding = CUTOVER.snapshot_evidence_binding(
            evidence_entry, "incumbent_zone_snapshot", "0" * 64, captured
        )
        self.assertTrue(binding["matches"])

        with self.assertRaisesRegex(ValueError, "observation time"):
            CUTOVER.snapshot_evidence_binding(
                evidence_entry,
                "incumbent_zone_snapshot",
                "0" * 64,
                datetime(2026, 8, 22, 11, 0, tzinfo=timezone.utc),
            )

    def test_release_candidate_requires_full_lowercase_commit(self) -> None:
        with self.assertRaises(RELEASE_CANDIDATE.CandidateError):
            RELEASE_CANDIDATE.resolve_exact_commit(ROOT, "abc123")


if __name__ == "__main__":
    unittest.main()
