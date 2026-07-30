# MeshFlow Contracts

Shared Pydantic contracts used by Core, Gateway, and MeshFlow apps.

Rule of thumb: if a model is only used by one app, it does not belong here.

## Installation

`0.2.3` is published on PyPI and is the currently supported line:
`pip install "meshflow-contracts~=0.2.3"`.

`0.3.0` is prepared but not yet published. Consumers must not assume it is
available, and must not adopt it before its public wheel, sdist, hashes, and
provenance are verified.

Maintainers: use the package-specific [release and adoption runbook](RELEASING.md).

## External ingress manifests

Apps may declare optional generic external ingress capabilities through
`AppManifest.external_ingress`. Each entry fixes the audience, private upstream
path, methods, content types, scopes, body limit, and rate policy that platform
services may snapshot and enforce. The contract describes policy only; it does
not route traffic or authorize grants.

Manifests that omit `external_ingress` remain valid and declare no external
ingress capabilities.

External ingress policy is intentionally conservative for Core/Gateway
snapshots: internal upstream paths must be canonical absolute app-internal
paths, capability ids are unique per manifest, methods are limited to `GET`,
`POST`, `PUT`, and `DELETE`, and numeric limits are strict integers. Contract
safety caps are 100 MiB per request body, 1,000 requests per window, and 3,600
seconds per rate window.

## Integration request tokens

`IntegrationRequestClaims` defines the shared internal JWT payload Gateway sends
only to private app ingress after Core has validated an integration grant. The
contract adds `token_type="integration_request"` without changing existing
`app_request` or `lifecycle` token claims.

The claims model requires workspace, installation, app/audience, capability,
grant, subject user, request, `jti`, immutable scopes, and strict integer `iat`
/ `exp` values. App id and audience must match, token lifetime is capped at
3,600 seconds, undeclared claims are rejected, and validated copies re-run the
same invariants. JWT registered claims keep their JWT semantics: `iss` accepts a
case-sensitive non-empty StringOrURI, including HTTPS URIs and arbitrary
human-readable no-colon issuer strings, while `sub` and `jti` are case-sensitive
opaque URL-safe strings rather than MeshFlow identifiers. This package validates
claim shape only; cryptographic verification and equality to the configured
issuer remain runtime responsibilities alongside signing, minting, JWKS
validation, replay handling, routing, lifecycle status, error taxonomy, and grant
persistence.

## 0.3.0 rollout notes

`0.3.0` removes `service.base_url` from `AppManifest`. The manifest now describes
app identity only; the upstream address is a deployment binding supplied
separately at registration time. Consumers must migrate their own manifest
producers before adopting.

`ServiceDefinition` stays tolerant of unknown keys on purpose. Registry manifest
snapshots are immutable and hashed at write time, and Core parses them on the
read path, so a snapshot written by `0.2.x` has to keep parsing. Refusing a newly
submitted manifest that still carries `base_url` is a registration-time policy
check in Core, not a contract-level rule.

Core adopts the verified package before Gateway; the schema upgrade alone does
not enable runtime capabilities.

The failed `v0.2.0`, `v0.2.1`, and `v0.2.2` tags are immutable unpublished
history. They must never be moved, reused, published, or turned into GitHub
Releases.

- Apps that omit `external_ingress` preserve `0.1.0` parse/serialize behavior;
  omission grants no public ingress.
- Registration and runtime rollout depend on Core/Gateway adopting their own
  snapshot, introspection, routing, and policy-enforcement behavior.
- Core/Gateway must ignore `external_ingress` until their own snapshot,
  introspection, routing, and policy-enforcement work lands.
- Apps must ignore `integration_request` until they implement private external
  ingress consumers; existing browser and lifecycle paths keep using
  `app_request` and `lifecycle` semantics.
- No Core, Gateway, or app domain behavior is enabled solely by upgrading this
  package.

Packaging metadata, licensing, source-level checks, strict artifact inspection, and
wheel/sdist smoke tests are enforced by release CI before consumer adoption.

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).

Copyright 2026 MeshFlow contributors.
