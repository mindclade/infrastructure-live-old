# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
output "environment_apply_authority" {
  description = "Environment to scoped apply identity and folder."
  value = {
    for environment, folder in var.environment_folder_ids : environment => {
      folder          = folder
      service_account = var.environment_apply_service_accounts[environment]
    }
  }
}

output "supply_chain_service_accounts" {
  description = "Normal-plane builder/qualifier/signer/promoter service-account emails."
  value       = { for name, sa in google_service_account.supply_chain : name => sa.email }
}
