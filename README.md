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
