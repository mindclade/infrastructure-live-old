# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

resource "google_org_policy_policy" "boolean" {
  for_each = var.boolean_policies

  name   = "${var.parent}/policies/${each.key}"
  parent = var.parent

  spec {
    rules {
      enforce = each.value ? "TRUE" : "FALSE"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_org_policy_policy" "list" {
  for_each = var.list_policies

  name   = "${var.parent}/policies/${each.key}"
  parent = var.parent

  spec {
    rules {
      values {
        allowed_values = length(each.value.allowed_values) == 0 ? null : each.value.allowed_values
        denied_values  = length(each.value.denied_values) == 0 ? null : each.value.denied_values
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_org_policy_policy" "managed" {
  for_each = var.managed_policies

  name   = "${var.parent}/policies/${each.key}"
  parent = var.parent

  spec {
    rules {
      enforce = each.value.enforced ? "TRUE" : "FALSE"
      parameters = length(each.value.parameters) == 0 ? null : jsonencode(
        each.value.parameters
      )
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_org_policy_policy" "sandbox_external_ip_reset" {
  count = var.sandbox_external_ip_reset ? 1 : 0

  name   = "${var.sandbox_folder_id}/policies/compute.vmExternalIpAccess"
  parent = var.sandbox_folder_id

  spec {
    reset = true
  }

  lifecycle {
    prevent_destroy = true
  }
}
