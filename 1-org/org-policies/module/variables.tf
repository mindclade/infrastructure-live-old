# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

variable "parent" {
  description = "Organization resource name receiving the baseline policies."
  type        = string

  validation {
    condition     = can(regex("^organizations/[0-9]+$", var.parent))
    error_message = "parent must be organizations/<numeric-id>."
  }
}

variable "sandbox_folder_id" {
  description = "Network-isolated sandbox folder receiving the one approved policy reset."
  type        = string

  validation {
    condition     = can(regex("^folders/[0-9]+$", var.sandbox_folder_id))
    error_message = "sandbox_folder_id must be folders/<numeric-id>."
  }
}

variable "cloud_identity_customer_id" {
  description = "Immutable Cloud Identity customer ID allowed by domain-restricted sharing."
  type        = string
  sensitive   = false

  validation {
    condition     = can(regex("^C[0-9a-z]+$", var.cloud_identity_customer_id))
    error_message = "cloud_identity_customer_id must be a Cloud Identity customer ID beginning with C."
  }
}

variable "boolean_policies" {
  description = "Legacy and non-parameterized boolean constraints keyed by constraint name."
  type        = map(bool)
}

variable "list_policies" {
  description = "List constraints keyed by constraint name."
  type = map(object({
    allowed_values = list(string)
    denied_values  = list(string)
  }))

  validation {
    condition = alltrue([
      for policy in values(var.list_policies) :
      !(length(policy.allowed_values) > 0 && length(policy.denied_values) > 0)
    ])
    error_message = "a list policy may allow values or deny values, but not both."
  }
}

variable "managed_policies" {
  description = "Org Policy API v2 managed constraints with typed JSON parameters."
  type = map(object({
    enforced   = bool
    parameters = map(list(string))
  }))
}

variable "sandbox_external_ip_reset" {
  description = "Reset only compute.vmExternalIpAccess in the isolated sandbox folder."
  type        = bool
  default     = false
}
