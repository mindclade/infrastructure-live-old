# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

locals {
  environment      = "production"
  region           = get_env("PRIMARY_REGION", "us-central1")
  criticality      = "critical"
  security_profile = "production"
}
