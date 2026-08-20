#!/usr/bin/env bash
# Copyright © 2026 Mindclade, LLC. All Rights Reserved.
# Mindclade Proprietary and Confidential.
# SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary

# Plan only the units a PR actually touches.
#
# A repo-wide `run --all plan` across 70 units takes 30+ minutes and produces a comment
# nobody reads. This narrows it to the units whose own files changed, plus — importantly —
# every unit that DEPENDS on one of those, because a changed output propagates downstream.
#
#   ./scripts/plan-changed.sh [base-ref]
set -euo pipefail

BASE="${1:-origin/main}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

changed_files=$(git diff --name-only "${BASE}...HEAD")
if [ -z "$changed_files" ]; then
  echo "No changes against ${BASE}."
  exit 0
fi

# A change to root.hcl, account.hcl, or _envcommon affects everything. Narrowing in that
# case would be actively misleading — the PR comment would show three units when sixty are
# affected.
# Unit paths are REPO-RELATIVE WITH NO LEADING "./", everywhere in this script.
#
# That normalisation is load-bearing. `find .` yields "./4-projects/data" while `dirname` of a
# git path yields "4-projects/data", and the two branches below used to produce different
# forms. The dependent expansion further down keys an associative array on these strings, so
# the mismatch meant no dependency ever matched and dependents were never pulled in at all —
# silently, in exactly the branch the script exists for.
units_from_find() {
  find . -name terragrunt.hcl -not -path './.terragrunt-cache/*' -exec dirname {} \; \
    | sed 's|^\./||' | sort -u
}

if grep -qE '^(root\.hcl|account\.hcl|_envcommon/)' <<<"$changed_files"; then
  echo "Shared configuration changed — planning every unit."
  mapfile -t units < <(units_from_find)
else
  mapfile -t units < <(
    grep -E '/terragrunt\.hcl$|/[^/]+\.hcl$' <<<"$changed_files" \
      | xargs -r -n1 dirname \
      | sed 's|^\./||' \
      | sort -u \
      | while read -r d; do [ -f "$d/terragrunt.hcl" ] && echo "$d"; done
  )
fi

if [ ${#units[@]} -eq 0 ]; then
  echo "No terragrunt units affected."
  exit 0
fi

# Pull in dependents. A unit whose dependency changed may plan differently even though none
# of its own files moved — that is precisely the change worth surfacing on the PR.
declare -A selected
for u in "${units[@]}"; do selected["$u"]=1; done

# ---------------------------------------------------------------------------------------
# Dependency map, built once
# ---------------------------------------------------------------------------------------
# Resolving `config_path` means a subshell per edge. Doing that inside the fixed-point loop
# below would re-resolve the whole graph on every round; building it once turns the loop into
# array lookups.
declare -A deps_of
while IFS= read -r unit; do
  edges=""
  while IFS= read -r dep; do
    [ -z "$dep" ] && continue
    resolved=$(cd "$unit" && cd "$dep" 2>/dev/null && pwd) || {
      echo "::warning::$unit declares config_path \"$dep\", which does not resolve to a directory" >&2
      continue
    }
    # Same normalisation as units_from_find: repo-relative, no leading "./".
    edges+="${resolved#"$ROOT/"}"$'\n'
  done < <(grep -oE 'config_path *= *"[^"]+"' "$unit/terragrunt.hcl" 2>/dev/null | cut -d'"' -f2)
  deps_of["$unit"]="$edges"
done < <(units_from_find)

# ---------------------------------------------------------------------------------------
# Fixed point, not a single pass
# ---------------------------------------------------------------------------------------
# THE BUG THIS REPLACES, because it is subtle and it silently under-plans:
#
# The previous version walked every unit once, in `find` order, and selected a unit if any of
# its dependencies was already selected. With a chain A → B → C, if `find` happened to yield C
# before B, then C was examined while B was still unselected, B was selected a moment later,
# and C was never reconsidered. Whether a dependent got planned depended on directory
# ordering.
#
# That was survivable when one unit was implemented. It is not now: the graph is four levels
# deep (2-environments → 3-networks → 4-projects → 5-workloads), so a change to a shared
# project could pull in the network stage and drop everything below it — and the PR comment
# would list a subset while reading as complete coverage.
#
# Iterating until a round adds nothing is O(depth) passes over a graph of a few dozen units,
# which is free, and it is correct regardless of ordering.
round=0
while :; do
  round=$((round + 1))
  added=0

  for candidate in "${!deps_of[@]}"; do
    [ -n "${selected[$candidate]:-}" ] && continue
    while IFS= read -r resolved; do
      [ -z "$resolved" ] && continue
      if [ -n "${selected[$resolved]:-}" ]; then
        echo "  + $candidate (depends on $resolved)"
        selected["$candidate"]=1
        added=1
        break
      fi
    done <<<"${deps_of[$candidate]}"
  done

  [ "$added" -eq 0 ] && break

  # A cycle cannot occur — Terragrunt rejects one — but a bounded loop beats a CI job that
  # hangs if that ever stops being true.
  if [ "$round" -gt 50 ]; then
    echo "::error::dependent resolution did not converge after 50 rounds; suspect a dependency cycle" >&2
    exit 1
  fi
done

echo
echo "Planning ${#selected[@]} unit(s) (converged in ${round} round(s)):"
printf '  %s\n' "${!selected[@]}" | sort

status=0
for unit in $(printf '%s\n' "${!selected[@]}" | sort); do
  echo
  echo "════════ $unit ════════"
  # --queue-include-external=false: plan what was asked for, not the transitive closure of
  # every dependency, which would defeat the narrowing this script exists to do.
  if ! (cd "$unit" && terragrunt run \
    --provider-cache \
    --non-interactive \
    -- plan -input=false -no-color -lock-timeout=20m); then
    echo "::error::plan failed in $unit"
    status=1
  fi
done

exit "$status"
