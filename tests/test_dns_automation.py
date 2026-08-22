#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Tests for DNS portfolio policy and read-only delegation evidence."""

from __future__ import annotations

import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ERROR_CODE = re.compile(r"^\[DNS-[A-Z0-9-]+\] ")
sys.path.insert(0, str(ROOT / "scripts"))

import check_dns_delegation as delegation  # noqa: E402
import generate_dns_domains as domains_projection  # noqa: E402
import validate_dns_portfolio as portfolio  # noqa: E402


class DNSPortfolioTest(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = portfolio.load_inventory(portfolio.DEFAULT_INVENTORY)
        self.record_pins = portfolio.load_reviewed_record_pins()

    def ready_workspace_inventory(self) -> dict:
        inventory = copy.deepcopy(self.inventory)
        inventory["module_contract"]["release_status"] = "published"
        inventory["migration_window"] = {
            "status": "approved",
            "change_reference": "CHG-test",
            "starts_at": "2026-08-22T01:00:00Z",
            "ends_at": "2026-08-22T02:00:00Z",
        }
        for domain in inventory["domains"]:
            domain["activation_blockers"] = [
                blocker
                for blocker in domain["activation_blockers"]
                if blocker
                not in {
                    portfolio.MODULE_RELEASE_BLOCKER,
                    portfolio.MIGRATION_WINDOW_BLOCKER,
                }
            ]
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.com"
        )
        domain.update(
            {
                "inventory_complete": True,
                "delegation_ready": True,
                "activation_blockers": [],
            }
        )
        return inventory

    def test_committed_inventory_is_safe_and_matches_live_units(self) -> None:
        self.assertEqual(portfolio.validate_inventory(self.inventory), [])
        self.assertEqual(portfolio.validate_live_parity(self.inventory), [])
        self.assertEqual(portfolio.validate_shared_dns_hub_interface(), [])

    def test_committed_reviewed_record_pins_contract_is_valid(self) -> None:
        self.assertEqual(
            portfolio.validate_reviewed_record_pins_schema(self.record_pins), []
        )

    def test_reviewed_values_are_not_duplicated_in_validator_source(self) -> None:
        validator_source = (ROOT / "scripts/validate_dns_portfolio.py").read_text(
            encoding="utf-8"
        )
        for pin in self.record_pins["pins"]:
            match = pin["match"]
            for field in ("rrdatas", "rrdata_sha256"):
                for value in match.get(field, []):
                    self.assertNotIn(value, validator_source)

    def test_generated_domain_projection_is_current(self) -> None:
        expected = domains_projection.render(self.inventory)
        self.assertEqual(
            domains_projection.DEFAULT_OUTPUT.read_text(encoding="utf-8"), expected
        )

    def test_planned_module_ref_requires_an_activation_blocker(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.ai"
        )
        domain["activation_blockers"].remove(portfolio.MODULE_RELEASE_BLOCKER)
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-INVENTORY-POLICY] mindclade.ai: planned module ref requires the "
            "dns-module-ref-not-published blocker",
            errors,
        )

    def test_published_module_ref_rejects_stale_release_blockers(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["module_contract"]["release_status"] = "published"
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-INVENTORY-POLICY] mindclade.ai: remove the stale "
            "module-release activation blocker",
            errors,
        )

    def test_pending_domain_fails_a_cutover_readiness_gate(self) -> None:
        errors = portfolio.validate_inventory(
            self.inventory, require_ready={"mindclade.com"}
        )
        self.assertIn(
            "[DNS-INVENTORY-POLICY] mindclade.com: delegation is not ready", errors
        )

    def test_environment_naming_cannot_enable_wildcard_production_records(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["environment_naming"]["wildcard_production_records_allowed"] = True
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-INVENTORY-POLICY] environment_naming must define production, "
            "staging, and development "
            "mindclade.ai boundaries without wildcard production records",
            errors,
        )

    def test_unapproved_migration_requires_a_domain_blocker(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.dev"
        )
        domain["activation_blockers"].remove(portfolio.MIGRATION_WINDOW_BLOCKER)
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-INVENTORY-POLICY] mindclade.dev: unapproved migration requires the "
            "migration-window-not-approved blocker",
            errors,
        )

    def test_caa_record_rejects_an_unapproved_issuer(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.ai"
        )
        caa = next(record for record in domain["records"] if record["type"] == "CAA")
        caa["rrdatas"].append('0 issue "example.invalid"')
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-INVENTORY-POLICY] mindclade.ai: apex CAA must permit pki.goog "
            "and letsencrypt.org, "
            "forbid wildcards, and carry the security iodef contact",
            errors,
        )

    def test_no_mail_domain_must_fail_closed(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.ai"
        )
        mx = next(record for record in domain["records"] if record["type"] == "MX")
        mx["rrdatas"] = ["1 smtp.google.com."]
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-INVENTORY-POLICY] mindclade.ai: no-mail policy requires apex "
            "null MX '0 .'",
            errors,
        )

    def test_public_address_record_is_rejected_by_module_contract(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.studio"
        )
        domain["records"].append(
            {"name": "www", "type": "A", "ttl": 300, "rrdatas": ["192.0.2.10"]}
        )
        errors = portfolio.validate_inventory(inventory)
        self.assertTrue(
            any("requires exact public_record_allowlist membership" in error for error in errors)
        )

    def test_exact_squarespace_public_address_allowlist_is_accepted(self) -> None:
        self.assertEqual(portfolio.validate_inventory(self.inventory), [])

    def test_allowlisted_public_address_values_are_exact(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.ai"
        )
        address = next(record for record in domain["records"] if record["type"] == "A")
        address["rrdatas"] = ["203.0.113.10"]
        errors = portfolio.validate_inventory(inventory)
        self.assertTrue(
            any(
                "allowlisted public record apex-a must match the exact reviewed "
                "incumbent Squarespace record" in error
                for error in errors
            )
        )

    def test_allowlisted_public_cname_target_is_exact(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.dev"
        )
        cname = next(record for record in domain["records"] if record["type"] == "CNAME")
        cname["rrdatas"] = ["unreviewed.example."]
        errors = portfolio.validate_inventory(inventory)
        self.assertTrue(
            any(
                "allowlisted public record www-cname must match the exact reviewed "
                "incumbent Squarespace record" in error
                for error in errors
            )
        )

    def test_allowlisting_one_public_address_does_not_allow_another(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.ai"
        )
        domain["public_record_allowlist"] = ["apex-a"]
        errors = portfolio.validate_inventory(inventory)
        self.assertTrue(
            any(
                "public CNAME record key www-cname requires exact "
                "public_record_allowlist membership" in error
                for error in errors
            )
        )

    def test_wildcard_public_address_owner_is_rejected(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.ai"
        )
        cname = next(record for record in domain["records"] if record["type"] == "CNAME")
        cname["name"] = "*"
        errors = portfolio.validate_inventory(inventory)
        self.assertTrue(any("may not use a wildcard owner" in error for error in errors))

    def test_stale_public_record_allowlist_entry_is_rejected(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.dev"
        )
        domain["public_record_allowlist"].append("missing-a")
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-INVENTORY-POLICY] mindclade.dev: public_record_allowlist entry "
            "missing-a must match "
            "exactly one A, AAAA, or CNAME record",
            errors,
        )

    def test_google_verification_must_be_retained_with_no_mail_spf(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item
            for item in inventory["domains"]
            if item["domain"] == "mindclade.studio"
        )
        apex_txt = next(
            record
            for record in domain["records"]
            if record["name"] == "@" and record["type"] == "TXT"
        )
        apex_txt["rrdatas"] = ["v=spf1 -all"]
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-PINS-103] mindclade.studio: reviewed pin "
            "mindclade-studio-google-verification RRdata mismatch",
            errors,
        )

    def test_google_verification_value_is_exact(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.dev"
        )
        apex_txt = next(
            record
            for record in domain["records"]
            if record["name"] == "@" and record["type"] == "TXT"
        )
        apex_txt["rrdatas"][-1] = "google-site-verification=unreviewed"
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-PINS-103] mindclade.dev: reviewed pin "
            "mindclade-dev-google-verification RRdata mismatch",
            errors,
        )
        self.assertNotIn("unreviewed", "\n".join(errors))

    def test_google_verification_ttl_is_exact(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.dev"
        )
        apex_txt = next(
            record
            for record in domain["records"]
            if record["name"] == "@" and record["type"] == "TXT"
        )
        apex_txt["ttl"] = 300
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-PINS-102] mindclade.dev: reviewed pin "
            "mindclade-dev-google-verification TTL mismatch",
            errors,
        )

    def test_no_mail_dmarc_requires_strict_alignment(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.ai"
        )
        dmarc = next(
            record
            for record in domain["records"]
            if record["name"] == "_dmarc" and record["type"] == "TXT"
        )
        dmarc["rrdatas"] = ["v=DMARC1; p=reject; sp=reject"]
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-INVENTORY-POLICY] mindclade.ai: no-mail policy requires exact "
            "DMARC p=reject, "
            "sp=reject, adkim=s, and aspf=s",
            errors,
        )

    def test_no_mail_dmarc_rejects_policy_weakening_tags(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.ai"
        )
        dmarc = next(
            record
            for record in domain["records"]
            if record["name"] == "_dmarc" and record["type"] == "TXT"
        )
        dmarc["rrdatas"] = [
            "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s; pct=0"
        ]
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "[DNS-INVENTORY-POLICY] mindclade.ai: no-mail policy requires exact "
            "DMARC p=reject, "
            "sp=reject, adkim=s, and aspf=s",
            errors,
        )

    def test_schema_rejects_unexpected_nested_property(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["certificate_policy"]["unreviewed"] = True
        errors = portfolio.validate_inventory(inventory)
        self.assertTrue(
            any(
                error.startswith(
                    "[DNS-INVENTORY-SCHEMA] schema $.certificate_policy:"
                )
                and "additionalProperties constraint failed" in error
                for error in errors
            )
        )

    def test_schema_requires_each_domain_exactly_once(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["domains"][1] = copy.deepcopy(inventory["domains"][0])
        errors = portfolio.validate_inventory_schema(inventory)
        self.assertTrue(
            any(
                error.startswith("[DNS-INVENTORY-SCHEMA] schema $.domains:")
                and "contains constraint failed" in error
                for error in errors
            )
        )

    def test_schema_errors_do_not_emit_record_values(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["domains"][1] = copy.deepcopy(inventory["domains"][0])
        record_values = {
            value
            for domain in inventory["domains"]
            for record in domain["records"]
            for value in record["rrdatas"]
        }
        errors = portfolio.validate_inventory_schema(inventory)
        self.assertTrue(errors)
        for error in errors:
            for record_value in record_values:
                self.assertNotIn(record_value, error)

    def test_inventory_diagnostics_are_coded_and_redacted(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["schema_version"] = 999
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.dev"
        )
        apex_txt = next(
            record
            for record in domain["records"]
            if record["name"] == "@" and record["type"] == "TXT"
        )
        injected_value = "google-site-verification=must-not-appear-in-diagnostics"
        apex_txt["rrdatas"][-1] = injected_value

        errors = portfolio.validate_inventory(inventory)

        self.assertTrue(errors)
        for error in errors:
            self.assertRegex(error, ERROR_CODE)
            self.assertNotIn(injected_value, error)

    def test_public_validation_boundaries_emit_stable_codes(self) -> None:
        with self.assertRaises(portfolio.InventoryError) as raised:
            portfolio.load_inventory(ROOT / "contracts/missing-dns-inventory.json")
        self.assertRegex(str(raised.exception), r"^\[DNS-INVENTORY-LOAD\] ")

        parity_errors = portfolio.validate_live_parity({"domains": None})
        self.assertTrue(parity_errors)
        self.assertTrue(
            all(error.startswith("[DNS-LIVE-PARITY] ") for error in parity_errors)
        )

        hub_errors = portfolio.validate_shared_dns_hub_interface(
            ROOT / "3-networks/shared/missing-dns-hub.hcl"
        )
        self.assertTrue(hub_errors)
        self.assertTrue(
            all(error.startswith("[DNS-HUB-INTERFACE] ") for error in hub_errors)
        )

    def test_record_pins_schema_requires_every_reviewed_identity(self) -> None:
        record_pins = copy.deepcopy(self.record_pins)
        record_pins["pins"].pop()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record-pins.json"
            path.write_text(json.dumps(record_pins), encoding="utf-8")
            errors = portfolio.validate_inventory(
                self.inventory, record_pins_path=path
            )
        self.assertTrue(
            any(error.startswith("[DNS-PINS-003]") for error in errors)
        )
        pinned_values = {
            value
            for pin in record_pins["pins"]
            for field in ("rrdatas", "rrdata_sha256")
            for value in pin["match"].get(field, [])
        }
        for error in errors:
            for pinned_value in pinned_values:
                self.assertNotIn(pinned_value, error)

    def test_missing_record_pins_contract_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            errors = portfolio.validate_inventory(
                self.inventory,
                record_pins_path=Path(directory) / "missing-record-pins.json",
            )
        self.assertTrue(
            any(error.startswith("[DNS-PINS-001]") for error in errors)
        )

    def test_missing_reviewed_record_emits_stable_code(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.com"
        )
        domain["records"] = [
            record
            for record in domain["records"]
            if not (
                record["name"] == "google._domainkey" and record["type"] == "TXT"
            )
        ]

        errors = portfolio.validate_inventory(inventory)

        self.assertIn(
            "[DNS-PINS-101] mindclade.com: reviewed pin "
            "mindclade-com-google-workspace-dkim record is missing",
            errors,
        )

    def test_record_pins_contract_root_must_be_an_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record-pins.json"
            path.write_text("[]", encoding="utf-8")
            errors = portfolio.validate_inventory(
                self.inventory, record_pins_path=path
            )
        self.assertEqual(
            [error for error in errors if error.startswith("[DNS-PINS-")],
            [
                "[DNS-PINS-002] reviewed record-pins root must be a JSON object"
            ],
        )

    def test_workspace_readiness_requires_complete_mail_authentication(self) -> None:
        inventory = self.ready_workspace_inventory()
        self.assertEqual(
            portfolio.validate_inventory(inventory, {"mindclade.com"}), []
        )

    def test_workspace_mx_values_are_exact(self) -> None:
        inventory = self.ready_workspace_inventory()
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.com"
        )
        mx = next(record for record in domain["records"] if record["type"] == "MX")
        mx["rrdatas"] = ["1 smtp.google.com."]
        errors = portfolio.validate_inventory(inventory, {"mindclade.com"})
        self.assertIn(
            "[DNS-PINS-103] mindclade.com: reviewed pin "
            "mindclade-com-google-workspace-mx RRdata mismatch",
            errors,
        )

    def test_workspace_dkim_value_is_exact(self) -> None:
        inventory = self.ready_workspace_inventory()
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.com"
        )
        dkim = next(
            record
            for record in domain["records"]
            if record["name"] == "google._domainkey"
        )
        dkim["rrdatas"] = ["v=DKIM1;k=rsa;p=unreviewed"]
        errors = portfolio.validate_inventory(inventory, {"mindclade.com"})
        self.assertIn(
            "[DNS-PINS-103] mindclade.com: reviewed pin "
            "mindclade-com-google-workspace-dkim RRdata mismatch",
            errors,
        )
        self.assertNotIn("unreviewed", "\n".join(errors))

    def test_workspace_dkim_owner_set_is_closed(self) -> None:
        inventory = self.ready_workspace_inventory()
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.com"
        )
        domain["records"].append(
            {
                "name": "unreviewed._domainkey",
                "type": "TXT",
                "ttl": 300,
                "rrdatas": ["v=DKIM1;k=rsa;p=unreviewed"],
            }
        )
        errors = portfolio.validate_inventory(inventory, {"mindclade.com"})
        self.assertIn(
            "[DNS-PINS-104] mindclade.com: reviewed Workspace DKIM owner set mismatch",
            errors,
        )
        self.assertNotIn("v=DKIM1;k=rsa;p=unreviewed", "\n".join(errors))


class DNSDelegationTest(unittest.TestCase):
    def test_txt_chunks_are_compared_as_one_value(self) -> None:
        value = '"v=DKIM1; p=first" "second"'
        self.assertEqual(
            delegation.canonical_rdata("TXT", value), "v=DKIM1; p=firstsecond"
        )

    def test_preflight_detects_incumbent_drift(self) -> None:
        inventory = {
            "domains": [
                {
                    "domain": "example.com",
                    "records": [
                        {
                            "name": "@",
                            "type": "TXT",
                            "rrdatas": ["v=spf1 -all"],
                        }
                    ],
                }
            ]
        }

        def resolver(server: str | None, name: str, record_type: str):
            if record_type == "SOA":
                return ["ns.example. hostmaster.example. 1 2 3 4 5"], None
            if server == "old.example.":
                return ["v=spf1 include:unexpected.example -all"], None
            return ["v=spf1 -all"], None

        checks = delegation.evaluate_delegation(
            inventory,
            "example.com",
            "preflight",
            ["old.example."],
            ["new.example."],
            False,
            resolver,
        )
        self.assertFalse(all(check["passed"] for check in checks))
        self.assertTrue(
            any(
                check["name"].startswith("incumbent:") and not check["passed"]
                for check in checks
            )
        )

    def test_preflight_ignores_provider_owned_snapshot_records(self) -> None:
        inventory = {
            "domains": [
                {
                    "domain": "example.com",
                    "records": [
                        {"name": "@", "type": "MX", "rrdatas": ["0 ."]}
                    ],
                }
            ]
        }
        snapshot = [
            {
                "name": "example.com.",
                "type": "NS",
                "rrdatas": ["new.example."],
            },
            {
                "name": "example.com.",
                "type": "MX",
                "rrdatas": ["0 ."],
            },
        ]

        def resolver(server: str | None, name: str, record_type: str):
            if record_type == "SOA":
                return ["ns.example. hostmaster.example. 1 2 3 4 5"], None
            if record_type == "MX":
                return ["0 ."], None
            self.fail(f"preflight must not compare provider-owned {record_type}")

        checks = delegation.evaluate_delegation(
            inventory,
            "example.com",
            "preflight",
            ["old.example."],
            ["new.example."],
            False,
            resolver,
            snapshot,
        )
        self.assertTrue(all(check["passed"] for check in checks))

    def test_postcutover_checks_delegation_records_and_dnssec(self) -> None:
        inventory = {
            "domains": [
                {
                    "domain": "example.com",
                    "records": [
                        {
                            "name": "@",
                            "type": "MX",
                            "rrdatas": ["0 ."],
                        }
                    ],
                }
            ]
        }

        def resolver(server: str | None, name: str, record_type: str):
            answers = {
                "NS": ["new.example."],
                "SOA": ["new.example. hostmaster.example. 1 2 3 4 5"],
                "MX": ["0 ."],
                "DS": ["12345 8 2 ABCD"],
                "DNSKEY": ["257 3 8 PUBLICKEY"],
            }
            return answers[record_type], None

        checks = delegation.evaluate_delegation(
            inventory,
            "example.com",
            "postcutover",
            [],
            ["new.example."],
            True,
            resolver,
        )
        self.assertTrue(all(check["passed"] for check in checks))

    def test_predeligation_requires_parent_ds_absence_and_target_agreement(self) -> None:
        inventory = {
            "domains": [{"domain": "example.com", "records": []}]
        }
        snapshot = [
            {
                "name": "example.com.",
                "type": "MX",
                "rrdatas": ["0 ."],
            }
        ]

        def resolver(server: str | None, name: str, record_type: str):
            if name == "com." and record_type == "NS":
                return ["a.gtld-servers.net."], None
            if server == "a.gtld-servers.net." and record_type == "DS":
                return [], None
            answers = {
                "SOA": ["ns.example. hostmaster.example. 1 2 3 4 5"],
                "DNSKEY": ["257 3 8 PUBLICKEY"],
                "MX": ["0 ."],
            }
            return answers[record_type], None

        checks = delegation.evaluate_delegation(
            inventory,
            "example.com",
            "predeligation",
            [],
            ["new.example."],
            False,
            resolver,
            snapshot,
        )
        self.assertTrue(all(check["passed"] for check in checks))

    def test_predeligation_fails_when_parent_ds_remains(self) -> None:
        inventory = {"domains": [{"domain": "example.com", "records": []}]}

        def resolver(server: str | None, name: str, record_type: str):
            if name == "com." and record_type == "NS":
                return ["a.gtld-servers.net."], None
            if server == "a.gtld-servers.net." and record_type == "DS":
                return ["12345 8 2 ABCD"], None
            return ["present"], None

        checks = delegation.evaluate_delegation(
            inventory,
            "example.com",
            "predeligation",
            [],
            ["new.example."],
            False,
            resolver,
            [{"name": "example.com.", "type": "MX", "rrdatas": ["present"]}],
        )
        self.assertTrue(
            any(check["name"].endswith("DS-absent") and not check["passed"] for check in checks)
        )


if __name__ == "__main__":
    unittest.main()
