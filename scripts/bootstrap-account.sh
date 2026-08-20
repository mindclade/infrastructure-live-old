#!/usr/bin/env bash
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOOTSTRAP_DIR="${BOOTSTRAP_DIR:-${1:-${ROOT}/../bootstrap}}"
TARGET="${TARGET:-${ROOT}/.account.env}"
command -v terraform >/dev/null || { echo 'terraform is required' >&2; exit 2; }
command -v jq >/dev/null || { echo 'jq is required' >&2; exit 2; }
[[ -d "$BOOTSTRAP_DIR" ]] || { echo "bootstrap repo not found: $BOOTSTRAP_DIR" >&2; exit 2; }
outputs="$(terraform -chdir="$BOOTSTRAP_DIR" output -json)"
value(){ jq -er --arg k "$1" '.[$k].value' <<<"$outputs"; }
state="$(value state_buckets)"; accounts="$(value service_accounts)"
q(){ printf '%q' "$1"; }
umask 077
tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
{
 echo '# Generated from verified bootstrap outputs. Contains identifiers only; never commit.'
 printf 'export GCP_ORG_ID=%s\n' "$(q "$(value org_id)")"
 printf 'export BILLING_ACCOUNT=%s\n' "$(q "$(value billing_account)")"
 printf 'export BOOTSTRAP_SEED_PROJECT_ID=%s\n' "$(q "$(value seed_project_id)")"
 printf 'export BOOTSTRAP_CICD_PROJECT_ID=%s\n' "$(q "$(value cicd_project_id)")"
 printf 'export BOOTSTRAP_CICD_PROJECT_NUMBER=%s\n' "$(q "$(value cicd_project_number)")"
 printf 'export GITHUB_WIF_POOL_NAME=%s\n' "$(q "$(value github_wif_pool_name)")"
 printf 'export TFSTATE_BUCKET_DEVELOPMENT=%s\n' "$(q "$(jq -er '.["infrastructure-live-development"]' <<<"$state")")"
 printf 'export TFSTATE_BUCKET_STAGING=%s\n' "$(q "$(jq -er '.["infrastructure-live-staging"]' <<<"$state")")"
 printf 'export TFSTATE_BUCKET_PRODUCTION=%s\n' "$(q "$(jq -er '.["infrastructure-live-production"]' <<<"$state")")"
 printf 'export SA_TF_LIVE_PLAN=%s\n' "$(q "$(jq -er '.["infrastructure-live-plan"]' <<<"$accounts")")"
 printf 'export SA_TF_LIVE_APPLY_FOUNDATION=%s\n' "$(q "$(jq -er '.["infrastructure-live-apply-foundation"]' <<<"$accounts")")"
 printf 'export SA_TF_LIVE_APPLY_DEVELOPMENT=%s\n' "$(q "$(jq -er '.["infrastructure-live-apply-development"]' <<<"$accounts")")"
 printf 'export SA_TF_LIVE_APPLY_STAGING=%s\n' "$(q "$(jq -er '.["infrastructure-live-apply-staging"]' <<<"$accounts")")"
 printf 'export SA_TF_LIVE_APPLY_PRODUCTION=%s\n' "$(q "$(jq -er '.["infrastructure-live-apply-production"]' <<<"$accounts")")"
 printf 'export STATE_LOCATION=%s\n' "$(q "$(value state_bucket_location)")"
 printf 'export MONOREPO_ORG=%s\n' "$(q "$(value github_org)")"
} >"$tmp"
mv "$tmp" "$TARGET"; trap - EXIT; chmod 0600 "$TARGET"
echo "wrote $TARGET; source it before Terragrunt commands"
