# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

include "root" { path = find_in_parent_folders("root.hcl") }
include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/bazel-remote-cache.hcl"
  merge_strategy = "deep"
}
