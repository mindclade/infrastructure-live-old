# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# Cloud KMS key ring reserved for Binary Authorization attestor signing keys.
#
# The ring only. The KEYS in it are created by the `binauthz` module, not here, because each
# attestor key is bound to the attestor it signs for — declaring them here would split one
# object across two units and two state files.
#
# Org-scoped rather than per-environment: an attestation travels with an image digest across
# environments, so the key that signed it cannot belong to one of them. This is the same
# reason the ring survived the split of the former single `1-org/kms` unit into per-environment
# units — see docs/module-interface-contract.md.

include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "${include.root.locals.module_source_base}//kms?ref=${local.module_version}"
}

locals {
  module_version = "v0.1.1"
}

inputs = {
  project_id = include.root.locals.seed_project_id
  location   = include.root.locals.region

  key_ring_name = "${include.root.locals.prefix}-binauthz"

  # Deliberately empty. The binauthz module creates the attestor keys in this ring.
  keys         = {}
  signing_keys = {}

  labels = include.root.locals.common_labels
}
