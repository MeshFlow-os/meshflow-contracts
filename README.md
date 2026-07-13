# MeshFlow Contracts

Shared Pydantic contracts used by Core, Gateway, and MeshFlow apps.

Rule of thumb: if a model is only used by one app, it does not belong here.

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
