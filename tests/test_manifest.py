import json
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

from meshflow_contracts.manifest import AppManifest, ExternalIngressDefinition


class Legacy010Publisher(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str


class Legacy010ServiceDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_url: HttpUrl | str
    health_url: str
    manifest_url: str
    openapi_url: str


class Legacy010NavigationEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    label: str
    path: str
    icon: str | None = None


class Legacy010NavigationDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entries: list[Legacy010NavigationEntry]


class Legacy010PermissionDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    description: str


class Legacy010SettingsDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sections: list[dict[str, Any]] = Field(default_factory=list)


class Legacy010AppManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str
    app_id: str
    slug: str
    name: str
    version: str
    publisher: Legacy010Publisher
    service: Legacy010ServiceDefinition
    navigation: Legacy010NavigationDefinition
    description: str | None = None
    permissions: list[Legacy010PermissionDefinition] = Field(default_factory=list)
    settings: Legacy010SettingsDefinition = Field(default_factory=Legacy010SettingsDefinition)
    triggers: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    ai_tools: list[dict[str, Any]] = Field(default_factory=list)


def manifest_data() -> dict[str, object]:
    return {
        "schema_version": "1",
        "app_id": "fitness",
        "slug": "fitness",
        "name": "Fitness",
        "version": "0.1.0",
        "publisher": {"name": "MeshFlow"},
        "service": {
            "base_url": "http://fitness-api:8000",
            "health_url": "/health",
            "manifest_url": "/manifest",
            "openapi_url": "/openapi.json",
        },
        "navigation": {"entries": []},
    }


LEGACY_MANIFEST_DUMP: dict[str, object] = {
    **manifest_data(),
    "description": None,
    "permissions": [],
    "settings": {"sections": []},
    "triggers": [],
    "actions": [],
    "jobs": [],
    "ai_tools": [],
}


def external_ingress_policy(**overrides: object) -> dict[str, object]:
    policy: dict[str, object] = {
        "capability_id": "health-import",
        "audience": "fitness",
        "allowed_methods": ["POST"],
        "allowed_content_types": ["application/json"],
        "internal_upstream_path": "/external/hae",
        "scopes": ["health:import"],
        "max_body_bytes": 10_000_000,
        "rate_policy": {"requests": 30, "window_seconds": 60},
    }
    policy.update(overrides)
    return policy


def test_manifest_accepts_external_ingress_policy() -> None:
    data = manifest_data()
    data["external_ingress"] = [external_ingress_policy()]

    manifest = AppManifest.model_validate(data)

    assert manifest.external_ingress[0].capability_id == "health-import"
    assert manifest.external_ingress[0].allowed_methods == ("POST",)
    assert manifest.model_dump()["external_ingress"][0]["allowed_methods"] == ["POST"]
    assert manifest.external_ingress[0].rate_policy.window_seconds == 60


def test_manifest_without_external_ingress_serializes_as_before() -> None:
    data = manifest_data()

    manifest = AppManifest.model_validate(data)

    assert manifest.external_ingress == ()
    assert manifest.model_dump(exclude_defaults=True) == data
    assert "external_ingress" not in manifest.model_dump()
    assert "external_ingress" not in json.loads(manifest.model_dump_json())


def test_legacy_010_manifest_fixture_preserves_ordinary_dump_and_json() -> None:
    legacy_manifest = AppManifest.model_validate(manifest_data())

    assert legacy_manifest.model_dump() == LEGACY_MANIFEST_DUMP
    assert json.loads(legacy_manifest.model_dump_json()) == LEGACY_MANIFEST_DUMP
    assert legacy_manifest.external_ingress == ()


def test_external_ingress_is_additive_for_consumers_that_ignore_unknown_fields() -> None:
    incoming_manifest = manifest_data()
    incoming_manifest["external_ingress"] = [external_ingress_policy()]

    serialized_manifest = AppManifest.model_validate(incoming_manifest).model_dump()
    legacy_consumer_manifest = Legacy010AppManifest.model_validate(serialized_manifest)
    consumer_view = legacy_consumer_manifest.model_dump()

    assert Legacy010AppManifest.model_config["extra"] == "ignore"
    assert "external_ingress" in serialized_manifest
    assert not hasattr(legacy_consumer_manifest, "external_ingress")
    assert consumer_view == LEGACY_MANIFEST_DUMP


@pytest.mark.parametrize(
    "internal_upstream_path",
    ["/external/hae", "/internal/v1/imports:submit", "/apps/fitness/external_hae-1"],
)
def test_external_ingress_accepts_canonical_internal_paths(internal_upstream_path: str) -> None:
    policy = ExternalIngressDefinition.model_validate(
        external_ingress_policy(internal_upstream_path=internal_upstream_path)
    )

    assert policy.internal_upstream_path == internal_upstream_path


@pytest.mark.parametrize(
    "internal_upstream_path",
    [
        "https://attacker.example/collect",
        "//attacker.example/collect",
        "/external//hae",
        "/external/../admin",
        "/external/./hae",
        "/external/%2e%2e/admin",
        "/external/%2Fadmin",
        "/external/%5cadmin",
        "/external/%252e%252e/admin",
        "/external\\..\\admin",
        "/external/hae/",
        "/external/hae?upstream=attacker",
        "/external/hae#fragment",
        "/external/hae tab",
        "/external/hae\n",
        "/external/hae\x00",
        "external/hae",
        "/",
    ],
)
def test_external_ingress_rejects_client_routable_upstream_paths(
    internal_upstream_path: str,
) -> None:
    with pytest.raises(ValidationError):
        ExternalIngressDefinition.model_validate(
            external_ingress_policy(internal_upstream_path=internal_upstream_path)
        )


@pytest.mark.parametrize("allowed_methods", [["post"], ["TRACE"], ["CONNECT"], ["PATCH"]])
def test_external_ingress_rejects_unsafe_http_methods(allowed_methods: list[str]) -> None:
    with pytest.raises(ValidationError):
        ExternalIngressDefinition.model_validate(external_ingress_policy(allowed_methods=allowed_methods))


@pytest.mark.parametrize("allowed_methods", [["POST"], ["GET", "POST"], ["PUT", "DELETE"]])
def test_external_ingress_accepts_safe_http_methods(allowed_methods: list[str]) -> None:
    policy = ExternalIngressDefinition.model_validate(
        external_ingress_policy(allowed_methods=allowed_methods)
    )

    assert policy.allowed_methods == tuple(allowed_methods)
    assert policy.model_dump()["allowed_methods"] == allowed_methods


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_body_bytes", "100"),
        ("max_body_bytes", True),
        ("max_body_bytes", 0),
        ("max_body_bytes", -1),
        ("max_body_bytes", 104_857_601),
        ("rate_policy", {"requests": "30", "window_seconds": 60}),
        ("rate_policy", {"requests": True, "window_seconds": 60}),
        ("rate_policy", {"requests": 0, "window_seconds": 60}),
        ("rate_policy", {"requests": 1_001, "window_seconds": 60}),
        ("rate_policy", {"requests": 30, "window_seconds": "60"}),
        ("rate_policy", {"requests": 30, "window_seconds": False}),
        ("rate_policy", {"requests": 30, "window_seconds": 0}),
        ("rate_policy", {"requests": 30, "window_seconds": 3_601}),
    ],
)
def test_external_ingress_rejects_non_strict_or_unsafe_numeric_limits(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        ExternalIngressDefinition.model_validate(external_ingress_policy(**{field: value}))


@pytest.mark.parametrize(
    "policy_overrides",
    [
        {"capability_id": "Health Import"},
        {"capability_id": "health/import"},
        {"capability_id": "-health-import"},
        {"audience": "Fitness"},
        {"audience": "fitness app"},
    ],
)
def test_external_ingress_rejects_invalid_capability_and_audience_identifiers(
    policy_overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ExternalIngressDefinition.model_validate(external_ingress_policy(**policy_overrides))


def test_manifest_rejects_duplicate_external_ingress_capability_ids() -> None:
    data = manifest_data()
    data["external_ingress"] = [
        external_ingress_policy(allowed_methods=["POST"]),
        external_ingress_policy(allowed_methods=["GET"], scopes=["health:read"]),
    ]

    with pytest.raises(ValidationError):
        AppManifest.model_validate(data)


@pytest.mark.parametrize(
    "policy_overrides",
    [
        {"allowed_methods": ["POST", "POST"]},
        {"allowed_content_types": ["application/json", "application/json"]},
        {"scopes": ["health:import", "health:import"]},
    ],
)
def test_external_ingress_rejects_duplicate_policy_values(
    policy_overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ExternalIngressDefinition.model_validate(external_ingress_policy(**policy_overrides))


def test_external_ingress_policy_is_immutable() -> None:
    policy = ExternalIngressDefinition.model_validate(external_ingress_policy())

    with pytest.raises(ValidationError):
        setattr(policy, "capability_id", "other")


def test_validated_external_ingress_policy_collections_cannot_be_mutated() -> None:
    policy = ExternalIngressDefinition.model_validate(
        external_ingress_policy(
            allowed_methods=["POST", "PUT"],
            allowed_content_types=["application/json", "application/x-ndjson"],
            scopes=["health:import", "health:write"],
        )
    )

    collection_cases = [
        (policy.allowed_methods, "append", "TRACE", ["POST", "PUT"]),
        (policy.allowed_content_types, "extend", "not-a-media-type", ["application/json", "application/x-ndjson"]),
        (policy.scopes, "append", "admin", ["health:import", "health:write"]),
    ]
    dump = policy.model_dump()

    for value, mutator, invalid_value, serialized in collection_cases:
        assert value == tuple(serialized)
        assert not hasattr(value, mutator)
        mutable_value: Any = value
        with pytest.raises(TypeError):
            mutable_value[0] = invalid_value

    assert dump["allowed_methods"] == ["POST", "PUT"]
    assert dump["allowed_content_types"] == ["application/json", "application/x-ndjson"]
    assert dump["scopes"] == ["health:import", "health:write"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("allowed_methods", []),
        ("allowed_methods", ["GET /admin"]),
        ("allowed_content_types", ["not-a-media-type"]),
        ("scopes", []),
        ("max_body_bytes", 0),
        ("rate_policy", {"requests": 0, "window_seconds": 60}),
    ],
)
def test_external_ingress_rejects_invalid_policy(field: str, value: object) -> None:
    policy = external_ingress_policy()
    policy[field] = value

    with pytest.raises(ValidationError):
        ExternalIngressDefinition.model_validate(policy)
