#!/usr/bin/env python3
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

"""Source contracts for the append-only production qualification archive."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProductionQualificationInfrastructureTest(unittest.TestCase):
    def test_reader_and_writer_authorities_are_separate(self) -> None:
        main = (
            ROOT / "5-workloads/shared/control-plane-identities/main.tf"
        ).read_text(encoding="utf-8")
        accessor = re.search(
            r'resource "google_secret_manager_secret_iam_member" '
            r'"production_qualification_reader" \{(.*?)\n\}',
            main,
            re.S,
        )
        self.assertIsNotNone(accessor)
        assert accessor is not None
        self.assertIn('role      = "roles/secretmanager.secretAccessor"', accessor.group(1))
        self.assertIn('production_qualification["reader"]', accessor.group(1))
        self.assertNotIn('production_qualification["writer"]', accessor.group(1))
        self.assertNotIn("roles/storage", main)

    def test_archive_is_create_only_locked_and_access_logged(self) -> None:
        evidence = (
            ROOT
            / "5-workloads/shared/production-qualification-evidence/terragrunt.hcl"
        ).read_text(encoding="utf-8")
        required = (
            'module_version = "v0.4.0"',
            'name                        = "${include.root.locals.prefix}-production-qualification-evidence"',
            'location                    = "US"',
            "versioning_enabled          = true",
            "create_only_workload        = true",
            "soft_delete_retention_days  = 90",
            "retention_period_seconds    = 220752000",
            "lock_retention_policy       = true",
            'retention_lock_confirmation = "LOCKING A CLOUD STORAGE RETENTION POLICY IS IRREVERSIBLE"',
            'access_log_object_prefix    = "production-qualification/"',
            'service_accounts["production_qualification_writer"]',
        )
        for fragment in required:
            self.assertIn(fragment, evidence)
        for forbidden in (
            "object_admins",
            "roles/storage.objectAdmin",
            "production_qualification_reader",
            'action        = "Delete"',
            'action        = "SetStorageClass"',
        ):
            self.assertNotIn(forbidden, evidence)

    def test_log_sink_and_cmek_are_separately_governed(self) -> None:
        logs = (
            ROOT
            / "5-workloads/shared/production-qualification-access-logs/terragrunt.hcl"
        ).read_text(encoding="utf-8")
        kms = (ROOT / "1-org/kms-dr-evidence/terragrunt.hcl").read_text(
            encoding="utf-8"
        )
        self.assertIn("production-qualification-evidence", logs)
        self.assertIn('object_creators = ["group:cloud-storage-analytics@google.com"]', logs)
        self.assertIn("lock_retention_policy       = true", logs)
        self.assertEqual(kms.count("production-qualification-evidence"), 2)
        self.assertIn('protection_level        = "HSM"', kms)
        self.assertIn("@gs-project-accounts.iam.gserviceaccount.com", kms)

    def test_new_units_have_provider_locks(self) -> None:
        for unit in (
            "5-workloads/shared/production-qualification-evidence",
            "5-workloads/shared/production-qualification-access-logs",
        ):
            self.assertTrue((ROOT / unit / ".terraform.lock.hcl").is_file(), unit)


if __name__ == "__main__":
    unittest.main()
