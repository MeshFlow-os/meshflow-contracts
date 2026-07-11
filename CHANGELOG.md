# Changelog
## 0.2.0

- Add the optional `external_ingress` app manifest contract.
- Preserve validation and compatible serialization for manifests that omit it.
- Reject duplicate capability ids, unsafe methods, non-strict numeric limits,
  and non-canonical private upstream paths.
- Document contract safety caps for body size and rate policy limits.
