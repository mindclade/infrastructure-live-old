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
import validate_dns_portfolio as portfolio  # noqa: E402


class DNSPortfolioTest(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = portfolio.load_inventory(portfolio.DEFAULT_INVENTORY)

    def test_committed_inventory_is_safe_and_matches_live_units(self) -> None:
        self.assertEqual(portfolio.validate_inventory(self.inventory), [])
        self.assertEqual(portfolio.validate_live_parity(self.inventory), [])

    def test_pending_domain_fails_a_cutover_readiness_gate(self) -> None:
        errors = portfolio.validate_inventory(
            self.inventory, require_ready={"mindclade.com"}
        )
        self.assertIn("mindclade.com: delegation is not ready", errors)

    def test_no_mail_domain_must_fail_closed(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        domain = next(
            item for item in inventory["domains"] if item["domain"] == "mindclade.ai"
        )
        domain["records"][0]["rrdatas"] = ["1 smtp.google.com."]
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
            any("public type A is not supported by the DNS module" in error for error in errors)
        )

    def test_module_contract_accepts_a_full_immutable_sha(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["module_contract"]["ref"] = "a" * 40
        self.assertFalse(
            any("module ref" in error for error in portfolio.validate_inventory(inventory))
        )

    def test_module_contract_rejects_a_moving_ref(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["module_contract"]["ref"] = "main"
        self.assertIn(
            "module ref must be an immutable semantic tag or full SHA",
            portfolio.validate_inventory(inventory),
        )

    def test_workspace_readiness_requires_complete_mail_authentication(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["module_contract"]["ref"] = "v0.2.0"
        inventory["module_contract"]["supports_record_name_override"] = True
        for domain in inventory["domains"]:
            domain["activation_blockers"] = [
                blocker
                for blocker in domain["activation_blockers"]
                if blocker != "dns-module-record-name-override-not-released"
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
                            "v=spf1 include:_spf.google.com ~all",
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
                        "rrdatas": ["v=DMARC1; p=none"],
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


if __name__ == "__main__":
    unittest.main()
