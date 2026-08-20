# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
terraform {
  required_version = ">= 1.15.0, < 1.16.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.41.0, < 8.0.0"
    }
  }
}
