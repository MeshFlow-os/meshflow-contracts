# Changelog

## 0.3.0

Breaking. Consumers stay pinned to `0.2.3` until this version is published and
verified; adoption order is Core, then Gateway, then apps.

- Remove `service.base_url` from `AppManifest`. The manifest is now a
  deployment-independent artifact describing app identity only; the upstream
  address is supplied separately at registration time and already lives on the
  registry's own `service_base_url` column.
- Keep `ServiceDefinition` tolerant of unknown keys so manifest snapshots already
  persisted by the registry stay readable. Those rows are immutable and hashed at
  write time, and Core parses them on the read path when resolving external
  ingress capabilities. Refusing a newly submitted manifest that still carries
  `base_url` is a registration-time policy check, not a contract-level rule.
- Validate `health_url`, `manifest_url`, and `openapi_url` as normalized absolute
  paths, reusing the same rules that guard external ingress upstream paths.
- Add the optional `store` listing block: `long_description`, `category` (closed
  `AppCategory` taxonomy), `icon_url`, `screenshots`, and publisher links.
  Asset URLs must be absolute and https.
- Add the optional `release_notes` field describing the manifest's own version.
- Export the manifest models from the package root, so consumers can use
  `from meshflow_contracts import AppManifest` instead of reaching into
  `meshflow_contracts.manifest`.
- Rename `INTERNAL_UPSTREAM_PATH_PATTERN` to `NORMALIZED_ABSOLUTE_PATH_PATTERN`,
  keeping the previous name as an alias.

## 0.2.3

- Remove the unsupported `gh api --fail-with-body` option from release evidence
  checks and exercise the runner's real `gh api` parser in read-only CI.
- Recover from immutable failed unpublished `v0.2.0`, `v0.2.1`, and `v0.2.2`
  attempts without moving or reusing their tags.

## 0.2.2

- Recover the failed unpublished `v0.2.0` and `v0.2.1` release attempts without
  reusing or moving either immutable tag.
- Correctly distinguish the annotated tag object SHA from its peeled release
  commit throughout local, remote, and dry-run release evidence validation.
- Record this version as a failed, unpublished, immutable release attempt. It
  must not be rerun, retagged, reused, published, or represented by a GitHub Release.

## 0.2.1

- Recover the failed unpublished `v0.2.0` release without changing its immutable
  tag or creating a GitHub Release for it.
- Build release distributions with a clean output directory and without uv's
  generated `dist/.gitignore`, while preserving the verifier's exact allowlist.
- Add a pinned-uv build, verifier, wheel, and sdist integration regression for
  isolated non-publishing CI verification.
- Keep consumer adoption blocked until the public `0.2.1` package is verified;
  Core adopts before Gateway.
- Record this version as a failed, unpublished, immutable release attempt. It
  must not be rerun, retagged, reused, published, or represented by a GitHub Release.

## 0.2.0

- Prepare Apache-2.0 licensing, public PyPI metadata, uv_build configuration,
  Pydantic 2 compatibility bounds, and typed-package metadata for release.
- Record this version as a failed, unpublished, immutable release attempt. It
  must not be retagged, published, or represented by a GitHub Release.
- Add the optional `external_ingress` app manifest contract.
- Preserve validation and compatible serialization for manifests that omit it.
- Reject duplicate capability ids, unsafe methods, non-strict numeric limits,
  and non-canonical private upstream paths.
- Document contract safety caps for body size and rate policy limits.
- Add the backward-compatible `integration_request` internal token type and
  `IntegrationRequestClaims` for Core/Gateway/app boundaries.
- Keep JWT registered claims case-sensitive, reject undeclared token claims, and
  validate copied integration request claims to preserve invariants.
- Preserve existing `app_request` and `lifecycle` claim parsing semantics.
- Add compatibility fixtures for `0.1.0` manifests and legacy internal-token
  serialization so rollout remains additive.
- Document adoption order: contracts first, Core/Gateway/app runtime behavior
  only after their own implementations opt in.
