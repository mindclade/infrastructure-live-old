#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Tests for DNS portfolio policy and read-only delegation evidence."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_dns_delegation as delegation  # noqa: E402
import generate_dns_domains as domains_projection  # noqa: E402
import validate_dns_portfolio as portfolio  # noqa: E402


class DNSPortfolioTest(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = portfolio.load_inventory(portfolio.DEFAULT_INVENTORY)

    def test_committed_inventory_is_safe_and_matches_live_units(self) -> None:
        self.assertEqual(portfolio.validate_inventory(self.inventory), [])
        self.assertEqual(portfolio.validate_live_parity(self.inventory), [])
        self.assertEqual(portfolio.validate_shared_dns_hub_interface(), [])

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
            "mindclade.ai: planned module ref requires the "
            "dns-module-ref-not-published blocker",
            errors,
        )

    def test_published_module_ref_rejects_stale_release_blockers(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["module_contract"]["release_status"] = "published"
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "mindclade.ai: remove the stale module-release activation blocker",
            errors,
        )

    def test_pending_domain_fails_a_cutover_readiness_gate(self) -> None:
        errors = portfolio.validate_inventory(
            self.inventory, require_ready={"mindclade.com"}
        )
        self.assertIn("mindclade.com: delegation is not ready", errors)

    def test_environment_naming_cannot_enable_wildcard_production_records(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["environment_naming"]["wildcard_production_records_allowed"] = True
        errors = portfolio.validate_inventory(inventory)
        self.assertIn(
            "environment_naming must define production, staging, and development "
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
            "mindclade.dev: unapproved migration requires the "
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
            "mindclade.ai: apex CAA must permit pki.goog and letsencrypt.org, "
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
            "mindclade.ai: no-mail policy requires apex null MX '0 .'", errors
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
            "mindclade.dev: public_record_allowlist entry missing-a must match "
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
            "mindclade.studio: apex TXT must retain a Google verification value",
            errors,
        )

    def test_workspace_readiness_requires_complete_mail_authentication(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["module_contract"]["ref"] = "v0.2.0"
        inventory["module_contract"]["release_status"] = "published"
        inventory["module_contract"]["supports_record_name_override"] = True
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
                    "dns-module-record-name-override-not-released",
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
                "records": [
                    {
                        "name": "@",
                        "type": "MX",
                        "ttl": 3600,
                        "rrdatas": ["1 smtp.google.com."],
                    },
                    {
                        "name": "@",
                        "type": "TXT",
                        "ttl": 3600,
                        "rrdatas": [
                            portfolio.FINAL_WORKSPACE_SPF,
                            "google-site-verification=public-token",
                        ],
                    },
                    {
                        "name": "google._domainkey",
                        "type": "TXT",
                        "ttl": 3600,
                        "rrdatas": ["v=DKIM1; k=rsa; p=public-key"],
                    },
                    {
                        "name": "_dmarc",
                        "type": "TXT",
                        "ttl": 3600,
                        "rrdatas": [portfolio.FINAL_WORKSPACE_DMARC],
                    },
                ],
            }
        )
        self.assertEqual(
            portfolio.validate_inventory(inventory, {"mindclade.com"}), []
        )


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
