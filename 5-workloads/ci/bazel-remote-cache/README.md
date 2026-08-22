# Common CI Bazel remote cache

This foundation-owned unit declares the private, CMEK-encrypted cache bucket used by the
internal monorepo's GitHub-hosted Bazel lanes. It consumes the existing shared cache access-log
bucket, the `ci_artifacts` key, and the separate reader/writer accounts created by
`1-org/automation-iam`. The reusable module remains pinned to planned contract `v0.4.0`; this
source does not assert that the tag is published or any resource is live.

## Activation hold

Do not configure a Bazel client to upload to this bucket yet. Bazel's HTTP cache client issues
ordinary `PUT` requests, while the reviewed module grants writers only
`roles/storage.objectCreator` and requires create-only, content-addressed publication with an
`ifGenerationMatch=0` precondition. A qualified immutable gateway or a separately reviewed cache
contract must reconcile those semantics and prove duplicate-write handling before uploads are
enabled. Reader activation is also held until the provider, service accounts, bucket, CMEK grant,
and access logging have connected evidence.

## Applied handoff

After the bootstrap `1.5.0` contract and this foundation scope are applied through protected
automation, export only the applied outputs rather than constructing names:

- `WIF_PROVIDER_BAZEL_CACHE`;
- `SA_BAZEL_CACHE_READER`;
- `SA_BAZEL_CACHE_WRITER`;
- the cache module's authenticated `https_uri` and `gs_uri` outputs.

Record positive impersonation for pull-request read and each trusted write route, plus negative
tests for cross-route impersonation, manual dispatch, tags, feature branches, altered workflow
identity, wrong repository IDs, and wrong audience. Preserve a cold rebuild and cache-loss test
before any cache becomes a required CI dependency.
