# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

output "organization_policy_names" {
  description = "Constraint name to managed organization policy resource name."
  value = merge(
    { for constraint, policy in google_org_policy_policy.boolean : constraint => policy.name },
    { for constraint, policy in google_org_policy_policy.list : constraint => policy.name },
    { for constraint, policy in google_org_policy_policy.managed : constraint => policy.name },
  )
}

output "sandbox_external_ip_reset_name" {
  description = "Folder policy reset resource name, or null when disabled."
  value       = try(google_org_policy_policy.sandbox_external_ip_reset[0].name, null)
}
