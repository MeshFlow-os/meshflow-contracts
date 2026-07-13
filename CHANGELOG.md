# Changelog
## 0.2.0

- Prepare Apache-2.0 licensing, public PyPI metadata, uv_build configuration,
  Pydantic 2 compatibility bounds, and typed-package metadata for release.
- Keep artifact build, inspection, and install/import smoke verification deferred
  to the R0.7/R0.9 release workflow gates; this version remains unreleased.
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
