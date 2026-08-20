# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

locals {
  environment      = "development"
  region           = get_env("PRIMARY_REGION", "us-central1")
  criticality      = "medium"
  security_profile = "development"
}
