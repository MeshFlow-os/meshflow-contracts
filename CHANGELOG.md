# Changelog
## 0.2.0

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
