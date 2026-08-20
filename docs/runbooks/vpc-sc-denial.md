<!-- Copyright © 2026 Mindclade, LLC. All Rights Reserved. Mindclade Proprietary and Confidential. SPDX-License-Identifier: LicenseRef-Mindclade-Proprietary -->

<!-- mindclade-doc: runbook@1 -->

# VPC Service Controls denial

> **Use when:** a Google API request is denied by a service perimeter or access level.
> **Impact:** the operation is blocked; an unexpected denial may indicate unauthorized access.
> **Owner:** workload owner with platform and security review.
> **Escalate:** immediately for an unexpected production caller or suspected perimeter drift.

## Symptoms

A Google API request fails with `PERIMETER_VIOLATION`, `NO_MATCHING_ACCESS_LEVEL`, or a
VPC Service Controls troubleshooting token.

## Impact

The denied operation is unavailable. Treat an unexpected production denial as a security
signal until audit evidence shows a missing approved access path.

## Diagnosis

1. Preserve the complete error, timestamp, caller, service, resource, source network, and
   troubleshooting token. Do not paste credentials or data payloads into the incident.
2. In the protected logging project, find the matching Access Context Manager/VPC-SC audit
   event and verify the authenticated principal and target resource.
3. Compare the event to the reviewed ingress and egress policy in
   `5-workloads/<environment>/vpc-sc-perimeter/terragrunt.hcl`.
4. Determine whether the caller should cross the boundary. A valid identity alone does not
   make the access path valid.

## Resolution

1. If access is not expected, contain the caller and follow the incident process.
2. If the path is expected, add the smallest identity, service, method, and resource scope in
   a reviewed pull request. Exercise it in dry-run/development and staging first.
3. Apply the exact saved plan through the foundation protected environment.
4. Confirm the original request succeeds and unrelated negative tests still fail.

Never disable a perimeter or add a wildcard as an incident shortcut. An emergency bypass
requires the production incident/change record, expiry, independent approval, and immediate
Git reconciliation.

## Prevention

Add the approved path to the VPC-SC integration fixtures and retain the negative test that
would detect a broader grant.

## Verify recovery

- The intended request succeeds through the exact approved identity, service, method, and resource.
- Unrelated callers, services, resources, and network paths remain denied.
- The applied plan matches the protected reviewed artifact.
- The incident/change record retains the troubleshooting token, audit event, policy delta, test
  results, approvers, and expiry/removal evidence for any emergency rule.

If the authenticated caller or target cannot be reconciled with the approved architecture, do not
change the perimeter. Preserve evidence and hand the incident to security.
