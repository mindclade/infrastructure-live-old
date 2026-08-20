# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

locals {
  environment      = "staging"
  region           = get_env("PRIMARY_REGION", "us-central1")
  criticality      = "high"
  security_profile = "staging"
}
