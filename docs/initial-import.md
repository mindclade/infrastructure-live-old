<!-- mindclade-doc: how-to@1 -->

# Import and activate the Infrastructure Live repository

> **Audience:** Infrastructure bootstrap operators  
> **Outcome:** Import the live tree, prove its account and module contracts, and activate
> protected scopes without recreating existing cloud resources.
> **Risk:** critical—incorrect imports or scope selection can replace organization and production
> resources.

## Prerequisites

- the existing `mindclade/infrastructure-live` repository and `.git` history;
- `.github` workflow release `v5.0.0`, completed Ring-0 bootstrap contract `1.4.0`, and applied
  `github-config` environments and variables;
- distinct plan and scope-specific apply identities with qualified negative tests;
- the exact immutable internal-monorepo module releases referenced by live units; and
- inventory and import decisions for any pre-existing Google Cloud resources.

Do not enable protected apply until account values have been generated from verified
bootstrap outputs and the target estate has been reconciled with Terraform state.

## Import and validate

1. Back up the current repository and record its default-branch commit.
2. Copy this tree into the existing checkout while preserving `.git`. Exclude `.account.env`,
   Terraform or Terragrunt caches, plans, state, credentials, and local overrides.
3. Generate the ignored account contract from the verified bootstrap checkout. The exporter
   fails closed unless the Ring-0 `platform_contract` version is exactly supported. Supply
   the immutable Cloud Identity customer ID that is already present in the organization-level
   `iam.allowedPolicyMemberDomains` policy; do not guess it from the domain name:

   ```sh
   CLOUD_IDENTITY_CUSTOMER_ID='<existing-customer-id>' \
     python3 scripts/bootstrap-account.py ../bootstrap
   ```

4. Enter the pinned shell, explicitly load the generated account contract into that shell, prove
   that the initial adoption phase is still `baseline`, and run structural validation. Do not rely
   on an earlier shell, direnv, or implicit environment inheritance:

   ```sh
   nix develop
   source ./.account.env
   python3 scripts/validate-account.py --runtime
   test "${ORG_POLICY_ACTIVATION_PHASE}" = baseline
   test -x "${TG_TF_PATH}"
   test "$("${TG_TF_PATH}" version -json | jq -r .terraform_version)" = \
     "$(tr -d '[:space:]' < .terraform-version)"
   make validate
   ```

   Remain inside this Nix shell for every Terragrunt command below. Both development shells set
   `TG_TF_PATH` to the repository's hash-pinned Terraform 1.15.9 derivation, so Terragrunt cannot
   select a different Terraform binary from the operator's `PATH`.

5. Validate immutable module interfaces against the approved internal monorepo checkout using
   the repository's module-interface script and contract.
6. Inventory existing resources one state unit at a time. Google automatically provisions a
   security baseline in newer organizations. Before changing the organization-policy state,
   verify that its production/foundation backend has object versioning enabled and record every
   existing generation for the exact state prefix. State metadata is not state content, but keep
   this evidence in a protected temporary directory anyway:

   ```sh
   cd 1-org/org-policies
   set -euo pipefail
   test "${ORG_POLICY_ACTIVATION_PHASE}" = baseline
   test -x "${TG_TF_PATH}"

   umask 077
   IMPORT_EVIDENCE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mindclade-policy-import.XXXXXX")"
   STATE_BUCKET="${TFSTATE_BUCKET_PRODUCTION}"
   STATE_OBJECT="gs://${STATE_BUCKET}/1-org/org-policies/default.tfstate"

   versioning_enabled="$(
     gcloud storage buckets describe "gs://${STATE_BUCKET}" \
       --raw --format='value(versioning.enabled)'
   )"
   case "${versioning_enabled}" in
     true|True) ;;
     *) echo "state bucket versioning is not enabled" >&2; exit 1 ;;
   esac

   state_versions="${IMPORT_EVIDENCE_DIR}/state-versions-before.txt"
   state_list_error="${IMPORT_EVIDENCE_DIR}/state-versions-before.stderr.txt"
   set +e
   gcloud storage ls --all-versions --long \
     "gs://${STATE_BUCKET}/1-org/org-policies/**" \
     >"${state_versions}" 2>"${state_list_error}"
   state_list_status=$?
   set -e
   prefix_status="$(
     python3 ../../scripts/classify-state-prefix.py \
       --status "${state_list_status}" \
       --stderr-file "${state_list_error}"
   )"
   case "${prefix_status}" in
     fresh) : >"${state_versions}" ;;
     existing-or-empty) ;;
     *) echo "invalid state-prefix classification" >&2; exit 1 ;;
   esac
   cat "${state_versions}"

   previous_generation=""
   if grep -Fq "${STATE_OBJECT}" "${state_versions}"; then
     previous_generation="$(
       gcloud storage objects describe "${STATE_OBJECT}" \
         --raw --format='value(generation)' \
         | tee "${IMPORT_EVIDENCE_DIR}/state-generation-before.txt"
     )"
     case "${previous_generation}" in
       ''|*[!0-9]*) echo "invalid current state generation" >&2; exit 1 ;;
     esac
   fi
   ```

   The explicit baseline environment also makes this unit set `skip_outputs = true` for its
   folders dependency and use only the sentinel folder outputs during `init`, `validate`,
   `import`, `plan`, and `show`; the uninitialized folders backend is not read. The command
   allowlist is exact: it permits rendering a saved plan or the current state for verification,
   but it does not permit `apply`, `destroy`, or any other mutation. Any absent value or the later
   `extended` phase sets `skip_outputs = false`, disables these mocks, and requires real folders
   state.

   Exit status `1` is accepted as a fresh prefix only when stderr is exactly
   `ERROR: (gcloud.storage.ls) One or more URLs matched no objects.` with an optional final newline.
   Extra warnings or any permission, authentication, network, retention, or metadata-read error
   are stop conditions, not evidence of an empty prefix. A successful empty listing is also
   acceptable. The exact-object lookup above is required whenever any version of that state
   object is listed; a listed object without a readable current numeric generation is therefore a
   stop condition rather than a fresh backend.

7. In `1-org/org-policies`, import only policies proven to exist, one at a time, into the exact v2
   address below. Immediately after each import, save a targeted plan and require zero managed
   resource actions for that address before continuing. Targeting is used only to isolate the
   just-imported object while the other six objects are not yet in state; never apply a targeted
   plan. The final step below requires a complete untargeted zero-change plan.

   ```sh
   test "${ORG_POLICY_ACTIVATION_PHASE}" = baseline
   test -n "${IMPORT_EVIDENCE_DIR:-}"
   test -n "${STATE_OBJECT:-}"

   import_and_verify_policy() {
     label="$1"
     address="$2"
     import_id="$3"
     plan_file="${IMPORT_EVIDENCE_DIR}/${label}.tfplan"
     plan_json="${IMPORT_EVIDENCE_DIR}/${label}.tfplan.json"

     terragrunt import "${address}" "${import_id}"
     new_generation="$(
       gcloud storage objects describe "${STATE_OBJECT}" \
         --raw --format='value(generation)' \
         | tee "${IMPORT_EVIDENCE_DIR}/state-generation-${label}.txt"
     )"
     case "${new_generation}" in
       ''|*[!0-9]*) echo "invalid state generation after ${label}" >&2; return 1 ;;
     esac
     if test -n "${previous_generation}"; then
       test "${new_generation}" != "${previous_generation}" || {
         echo "state generation did not advance after ${label}" >&2
         return 1
       }
       retained_generation="$(
         gcloud storage objects describe \
           "${STATE_OBJECT}#${previous_generation}" \
           --raw --format='value(generation)' \
           | tee "${IMPORT_EVIDENCE_DIR}/retained-generation-${label}.txt"
       )"
       test "${retained_generation}" = "${previous_generation}" || {
         echo "previous state generation was not retained after ${label}" >&2
         return 1
       }
     fi
     gcloud storage ls --all-versions --long "${STATE_OBJECT}" \
       | tee "${IMPORT_EVIDENCE_DIR}/state-versions-${label}.txt"
     previous_generation="${new_generation}"

     terragrunt plan \
       -input=false \
       -lock-timeout=20m \
       -target="${address}" \
       -out="${plan_file}"
     terragrunt show -json "${plan_file}" > "${plan_json}"
     jq -e --arg address "${address}" '
       ([
         .resource_changes[]? | select(.address == $address) | .change.actions
       ] == [["no-op"]]) and
       ([.resource_changes[]? | select(.change.actions != ["no-op"])] == [])
     ' "${plan_json}"
   }

   import_and_verify_policy allowed-member-domains \
     'google_org_policy_policy.list["iam.allowedPolicyMemberDomains"]' \
     "organizations/${GCP_ORG_ID}/policies/iam.allowedPolicyMemberDomains"
   import_and_verify_policy uniform-bucket-access \
     'google_org_policy_policy.boolean["storage.uniformBucketLevelAccess"]' \
     "organizations/${GCP_ORG_ID}/policies/storage.uniformBucketLevelAccess"
   import_and_verify_policy allowed-contact-domains \
     'google_org_policy_policy.managed["essentialcontacts.managed.allowedContactDomains"]' \
     "organizations/${GCP_ORG_ID}/policies/essentialcontacts.managed.allowedContactDomains"
   import_and_verify_policy disable-key-creation \
     'google_org_policy_policy.managed["iam.managed.disableServiceAccountKeyCreation"]' \
     "organizations/${GCP_ORG_ID}/policies/iam.managed.disableServiceAccountKeyCreation"
   import_and_verify_policy restrict-protocol-forwarding \
     'google_org_policy_policy.managed["compute.managed.restrictProtocolForwardingCreationForTypes"]' \
     "organizations/${GCP_ORG_ID}/policies/compute.managed.restrictProtocolForwardingCreationForTypes"
   import_and_verify_policy disable-default-sa-grants \
     'google_org_policy_policy.boolean["iam.automaticIamGrantsForDefaultServiceAccounts"]' \
     "organizations/${GCP_ORG_ID}/policies/iam.automaticIamGrantsForDefaultServiceAccounts"
   import_and_verify_policy disable-key-upload \
     'google_org_policy_policy.boolean["iam.disableServiceAccountKeyUpload"]' \
     "organizations/${GCP_ORG_ID}/policies/iam.disableServiceAccountKeyUpload"
   ```

   ### Resume after a completed import

   If an import completed and its new state generation was recorded, but verification stopped
   while rendering the targeted plan, that address is already state-owned. It must not be imported again.
   Resume only from the same protected evidence directory. The remote current
   generation must still equal the generation recorded immediately after the import; otherwise,
   stop because the state generation changed after the stopped import and reconcile who changed
   it before proceeding.

   Re-enter the pinned shell, reload `.account.env`, recreate the `STATE_OBJECT` value from step
   6, and redefine `import_and_verify_policy` from the preceding block without invoking it for an
   address already in state. Then verify the completed binding with this read-only helper:

   ```sh
   resume_verified_import() {
     label="$1"
     address="$2"
     recorded_generation_file="${IMPORT_EVIDENCE_DIR}/state-generation-${label}.txt"
     state_json="${IMPORT_EVIDENCE_DIR}/${label}-resume-state.json"
     plan_file="${IMPORT_EVIDENCE_DIR}/${label}-resume.tfplan"
     plan_json="${IMPORT_EVIDENCE_DIR}/${label}-resume.tfplan.json"

     test -s "${recorded_generation_file}" || {
       echo "missing recorded post-import state generation for ${label}" >&2
       return 1
     }
     recorded_generation="$(tr -d '[:space:]' < "${recorded_generation_file}")"
     current_generation="$(
       gcloud storage objects describe "${STATE_OBJECT}" \
         --raw --format='value(generation)'
     )"
     case "${current_generation}" in
       ''|*[!0-9]*) echo "invalid current state generation for ${label}" >&2; return 1 ;;
     esac
     test "${current_generation}" = "${recorded_generation}" || {
       echo "state generation changed after the stopped import for ${label}" >&2
       return 1
     }

     terragrunt show -json > "${state_json}"
     jq -e --arg address "${address}" '
       ([
         .values.root_module.resources[]?
         | select(.address == $address)
       ] | length) == 1
     ' "${state_json}"

     terragrunt plan \
       -input=false \
       -lock-timeout=20m \
       -target="${address}" \
       -out="${plan_file}"
     terragrunt show -json "${plan_file}" > "${plan_json}"
     jq -e --arg address "${address}" '
       ([
         .resource_changes[]? | select(.address == $address) | .change.actions
       ] == [["no-op"]]) and
       ([.resource_changes[]? | select(.change.actions != ["no-op"])] == [])
     ' "${plan_json}"

     previous_generation="${current_generation}"
   }

   resume_verified_import allowed-member-domains \
     'google_org_policy_policy.list["iam.allowedPolicyMemberDomains"]'
   ```

   Continue with only the first not-yet-imported call—`uniform-bucket-access` in this example—and
   then the remaining calls in order. Do not rerun `allowed-member-domains`. If the state address,
   recorded generation, remote generation, or fresh targeted no-op plan does not match exactly,
   stop rather than guessing where the sequence ended.

   Each successful import must create a new current generation while retaining the preceding
   generation in the all-versions listing. Stop on a missing generation, a non-no-op action for
   the selected address, or any unexpected policy value. After all seven imports, save and inspect
   the complete plan; it must contain no resource or output changes:

   ```sh
   full_plan="${IMPORT_EVIDENCE_DIR}/baseline-full.tfplan"
   full_plan_json="${IMPORT_EVIDENCE_DIR}/baseline-full.tfplan.json"
   terragrunt plan -input=false -lock-timeout=20m -out="${full_plan}"
   terragrunt show -json "${full_plan}" > "${full_plan_json}"
   jq -e '
     ([.resource_changes[]? | select(.change.actions != ["no-op"])] == []) and
     ([
       (.output_changes // {}) | to_entries[]?
       | select(.value.actions != ["no-op"])
     ] == [])
   ' "${full_plan_json}"
   ```

   Retain the protected plan files, JSON, state-generation listings, operator identity, and
   timestamps with the approved import change record, then remove the temporary directory from
   the workstation. Never commit these artifacts. `ORG_POLICY_ACTIVATION_PHASE=baseline` is
   deliberately cataloged for this adoption. Change it to `extended` only in a later reviewed
   governance change after every additional constraint passes Policy Simulator and lockout
   rehearsal. Extended-phase imports cannot use the mock folder output and therefore require the
   real `1-org/folders` state.
8. Import other approved existing resources
   into the matching unit; never accept a plan that recreates or deletes them merely to make
   the import fast.
9. Open a pull request and review affected plans in dependency order. Unexpected project,
   network, KMS, stateful storage, or production-cluster replacement is a stop condition.

## Activate by scope

1. Qualify the plan identity as read-oriented and unable to apply.
2. Qualify each apply identity against only its declared scope and protected environment.
3. Merge the reviewed import.
4. Confirm the push selects only the minimum expected scopes and creates exact one-day plan
   bundles for the merged commit.
5. Approve the first scope in dependency order. Start with required foundation units, then
   development, staging, and production; do not use a repository-wide simultaneous apply as
   an import shortcut.
6. Follow [production activation gates](production-activation-gates.md) before the first
   production mutation and [GitOps handoff](gitops-handoff.md) before Argo activation.

## Verify

- account and module-interface validation pass;
- applied plan context and checksums match the merged commit;
- each unit owns one expected state prefix and no cross-environment dependency appears;
- negative authorization tests prove scope identities cannot cross boundaries;
- fresh plans are empty after each activated scope; and
- `gitops` receives cloud prerequisites without this repository installing Kubernetes state.

The platform import order is `.github`, `bootstrap`, `github-config`,
`infrastructure-live`, then `gitops`.

## Roll back or recover

Before apply, remove an incorrect import from the isolated candidate state and replan. After an
approved import or mutation, prefer a reviewed forward correction; never delete state bindings to
make the plan green. For a failed production mutation follow
[the failed-apply runbook](runbooks/failed-production-apply.md), and for an orphaned lock follow
[the state-lock runbook](runbooks/state-lock-stuck.md).
