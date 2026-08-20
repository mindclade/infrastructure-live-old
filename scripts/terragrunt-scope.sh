#!/usr/bin/env bash
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary
#
# Create and apply an exact, checksummed Terragrunt plan bundle for one privilege scope.
set -euo pipefail

usage() {
  echo "usage: $0 <plan|apply> <foundation|development|staging|production|partners> <plan-dir> [unit]" >&2
  exit 2
}

[[ $# -ge 3 && $# -le 4 ]] || usage
MODE="$1"
SCOPE="$2"
PLAN_ROOT="$3"
UNIT="${4:-}"
[[ "$MODE" == plan || "$MODE" == apply ]] || usage

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
PLAN_ROOT="$(mkdir -p "$PLAN_ROOT" && cd "$PLAN_ROOT" && pwd)"

case "$SCOPE" in
  foundation) ROOTS=(
    "1-org"
    "3-networks/shared"
    "5-workloads/development/vpc-sc-perimeter"
    "5-workloads/staging/vpc-sc-perimeter"
    "5-workloads/production/vpc-sc-perimeter"
  ) ;;
  development) ROOTS=("2-environments/development" "3-networks/development" "4-projects/development" "5-workloads/development") ;;
  staging) ROOTS=("2-environments/staging" "3-networks/staging" "4-projects/staging" "5-workloads/staging") ;;
  production) ROOTS=("2-environments/production" "3-networks/production" "4-projects/production" "5-workloads/production" "5-workloads/shared") ;;
  partners) ROOTS=("4-projects/partners" "5-workloads/partners") ;;
  *) usage ;;
esac

is_foundation_special_unit() {
  case "$1" in
    5-workloads/development/vpc-sc-perimeter|5-workloads/development/vpc-sc-perimeter/*|\
    5-workloads/staging/vpc-sc-perimeter|5-workloads/staging/vpc-sc-perimeter/*|\
    5-workloads/production/vpc-sc-perimeter|5-workloads/production/vpc-sc-perimeter/*) return 0 ;;
    *) return 1 ;;
  esac
}

validate_unit() {
  local unit="$1" allowed=false root
  [[ -n "$unit" && "$unit" != /* && "$unit" != *..* && "$unit" != *\\* ]] || {
    echo "error: invalid unit path: $unit" >&2
    exit 2
  }
  [[ -f "$unit/terragrunt.hcl" ]] || {
    echo "error: no terragrunt.hcl at $unit" >&2
    exit 2
  }
  if is_foundation_special_unit "$unit"; then
    [[ "$SCOPE" == foundation ]] || {
      echo "error: VPC Service Controls units are foundation-owned" >&2
      exit 2
    }
  fi
  for root in "${ROOTS[@]}"; do
    if [[ "$unit" == "$root" || "$unit" == "$root/"* ]]; then
      allowed=true
      break
    fi
  done
  [[ "$allowed" == true ]] || {
    echo "error: unit $unit is outside scope $SCOPE" >&2
    exit 2
  }
}

if [[ -n "$UNIT" ]]; then
  validate_unit "$UNIT"
  ROOTS=("$UNIT")
fi

export TG_STRICT_MODE=true
export TG_NON_INTERACTIVE=true

run_root() {
  local root="$1"
  [[ -d "$root" ]] || return 0
  find "$root" -name terragrunt.hcl -type f -print -quit | grep -q . || return 0

  local key="${root//\//__}"
  local root_output="$PLAN_ROOT/$key"
  local plan_output="$root_output/plans"
  local json_output="$root_output/json"
  local -a filter_args=()
  mkdir -p "$plan_output" "$json_output"

  case "$root" in
    5-workloads/development|5-workloads/staging|5-workloads/production)
      filter_args=(--filter "!./vpc-sc-perimeter/**")
      ;;
  esac

  echo "::group::$MODE $SCOPE $root"
  if [[ "$MODE" == plan ]]; then
    nix develop .#ci --command terragrunt run --all \
      --provider-cache \
      --non-interactive \
      --queue-exclude-external \
      --working-dir "$root" \
      --out-dir "$plan_output" \
      --json-out-dir "$json_output" \
      "${filter_args[@]}" \
      -- plan -input=false -no-color -lock=false
  else
    nix develop .#ci --command terragrunt run --all \
      --provider-cache \
      --non-interactive \
      --queue-exclude-external \
      --working-dir "$root" \
      --out-dir "$plan_output" \
      "${filter_args[@]}" \
      -- apply -input=false -no-color -lock-timeout=20m
  fi
  echo "::endgroup::"
}

write_context() {
  python3 scripts/validate-account.py --runtime --json > "$PLAN_ROOT/ACCOUNT_RUNTIME.json"
  python3 - "$PLAN_ROOT/RUN_CONTEXT.json" "$SCOPE" "$UNIT" <<'PY'
import json, os, pathlib, subprocess, sys
output, scope, unit = sys.argv[1:]
commit = subprocess.run(
    ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True
).stdout.strip()
value = {
    "schema_version": "1.0.0",
    "repository": os.environ.get("GITHUB_REPOSITORY", "local"),
    "commit_sha": commit,
    "scope": scope,
    "unit": unit,
}
pathlib.Path(output).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
PY
}

verify_context() {
  local current_account current_commit planned_commit
  current_account="$(mktemp)"
  trap 'rm -f "$current_account"' RETURN
  python3 scripts/validate-account.py --runtime --json > "$current_account"
  cmp -s "$current_account" "$PLAN_ROOT/ACCOUNT_RUNTIME.json" || {
    echo "error: bootstrap-derived account inputs changed after the saved plan was created" >&2
    exit 1
  }
  current_commit="$(git rev-parse HEAD)"
  planned_commit="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit_sha"])' "$PLAN_ROOT/RUN_CONTEXT.json")"
  [[ "$current_commit" == "$planned_commit" ]] || {
    echo "error: saved plan belongs to $planned_commit, checked-out commit is $current_commit" >&2
    exit 1
  }
}

if [[ "$MODE" == plan ]]; then
  rm -rf "$PLAN_ROOT"
  mkdir -p "$PLAN_ROOT"
  for root in "${ROOTS[@]}"; do
    run_root "$root"
  done
  write_context
  python3 scripts/classify-plans.py "$PLAN_ROOT" --output "$PLAN_ROOT/PLAN_CLASSIFICATION.json"
  (
    cd "$PLAN_ROOT"
    find . -type f ! -name PLAN_SHA256SUMS -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 sha256sum > PLAN_SHA256SUMS
  )
  [[ -s "$PLAN_ROOT/PLAN_SHA256SUMS" ]] || {
    echo "error: no saved plans were generated for scope $SCOPE" >&2
    exit 1
  }
else
  for required in PLAN_SHA256SUMS ACCOUNT_RUNTIME.json RUN_CONTEXT.json PLAN_CLASSIFICATION.json; do
    [[ -s "$PLAN_ROOT/$required" ]] || {
      echo "error: saved plan bundle is missing $required" >&2
      exit 1
    }
  done
  (cd "$PLAN_ROOT" && sha256sum -c PLAN_SHA256SUMS)
  verify_context
  for root in "${ROOTS[@]}"; do
    run_root "$root"
  done
fi
