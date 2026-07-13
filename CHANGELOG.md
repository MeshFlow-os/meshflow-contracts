# Changelog
## 0.2.1

- Recover the failed unpublished `v0.2.0` release without changing its immutable
  tag or creating a GitHub Release for it.
- Build release distributions with a clean output directory and without uv's
  generated `dist/.gitignore`, while preserving the verifier's exact allowlist.
- Add a pinned-uv build, verifier, wheel, and sdist integration regression for
  isolated non-publishing CI verification.
- Keep consumer adoption blocked until the public `0.2.1` package is verified;
  Core adopts before Gateway.

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
