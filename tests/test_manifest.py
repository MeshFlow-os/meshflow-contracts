import json
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from meshflow_contracts.manifest import (
    AppCategory,
    AppManifest,
    ExternalIngressDefinition,
    ServiceDefinition,
    StoreListing,
    StoreScreenshot,
)


class Legacy020Publisher(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str


class Legacy020ServiceDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    health_url: str
    manifest_url: str
    openapi_url: str


class Legacy020NavigationEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    label: str
    path: str
    icon: str | None = None


class Legacy020NavigationDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entries: list[Legacy020NavigationEntry]


class Legacy020PermissionDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    description: str


class Legacy020SettingsDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sections: list[dict[str, Any]] = Field(default_factory=list)


class Legacy020AppManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str
    app_id: str
    slug: str
    name: str
    version: str
    publisher: Legacy020Publisher
    service: Legacy020ServiceDefinition
    navigation: Legacy020NavigationDefinition
    description: str | None = None
    permissions: list[Legacy020PermissionDefinition] = Field(default_factory=list)
    settings: Legacy020SettingsDefinition = Field(default_factory=Legacy020SettingsDefinition)
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
            "health_url": "/health",
            "manifest_url": "/manifest",
            "openapi_url": "/openapi.json",
        },
        "navigation": {"entries": []},
    }


BASELINE_MANIFEST_DUMP: dict[str, object] = {
    **manifest_data(),
    "description": None,
    "permissions": [],
    "settings": {"sections": []},
    "triggers": [],
    "actions": [],
    "jobs": [],
    "ai_tools": [],
}


def store_listing(**overrides: object) -> dict[str, object]:
    listing: dict[str, object] = {
        "long_description": "Track workouts, routines and progress over time.",
        "category": "health-and-fitness",
        "icon_path": "fitness/0.1.0/icon.png",
        "screenshots": [
            {"path": "fitness/0.1.0/1.png", "caption": "Today"},
            {"path": "fitness/0.1.0/2.png"},
        ],
        "website_url": "https://meshflow.example/fitness",
        "support_url": "https://meshflow.example/fitness/support",
        "privacy_policy_url": "https://meshflow.example/fitness/privacy",
    }
    listing.update(overrides)
    return listing


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


def test_minimal_manifest_preserves_ordinary_dump_and_json() -> None:
    minimal_manifest = AppManifest.model_validate(manifest_data())

    assert minimal_manifest.model_dump() == BASELINE_MANIFEST_DUMP
    assert json.loads(minimal_manifest.model_dump_json()) == BASELINE_MANIFEST_DUMP
    assert minimal_manifest.external_ingress == ()
    assert minimal_manifest.store_listing_path is None
    assert minimal_manifest.release_notes is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("external_ingress", [external_ingress_policy()]),
        ("store_listing_path", "fitness/store.json"),
        ("release_notes", "Adds recurring transactions."),
    ],
)
def test_optional_blocks_are_additive_for_consumers_that_ignore_unknown_fields(
    field: str, value: object
) -> None:
    incoming_manifest = manifest_data()
    incoming_manifest[field] = value

    serialized_manifest = AppManifest.model_validate(incoming_manifest).model_dump()
    legacy_consumer_manifest = Legacy020AppManifest.model_validate(serialized_manifest)
    consumer_view = legacy_consumer_manifest.model_dump()

    assert Legacy020AppManifest.model_config["extra"] == "ignore"
    assert field in serialized_manifest
    assert not hasattr(legacy_consumer_manifest, field)
    assert consumer_view == BASELINE_MANIFEST_DUMP


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


# --- service definition: deployment binding removed in 0.3.0 -----------------


def test_service_definition_drops_retired_base_url_without_rejecting_it() -> None:
    data = manifest_data()
    service = data["service"]
    assert isinstance(service, dict)
    service["base_url"] = "http://fitness-api:8000"

    manifest = AppManifest.model_validate(data)

    assert not hasattr(manifest.service, "base_url")
    assert "base_url" not in manifest.model_dump()["service"]


def test_persisted_0_2_x_snapshots_remain_readable() -> None:
    """Registry snapshots are immutable and hashed at write time.

    `AppManifest.model_validate` runs against them on the read path (Core resolves
    external ingress capabilities from the stored snapshot), so a manifest written
    by 0.2.x must keep parsing after the 0.3.0 removal or already-registered apps
    fail at request time rather than at deploy time.
    """
    persisted_snapshot = {
        **manifest_data(),
        "service": {
            "base_url": "http://healthapp-api:8000",
            "health_url": "/health",
            "manifest_url": "/manifest.json",
            "openapi_url": "/openapi.json",
        },
        "external_ingress": [external_ingress_policy()],
    }

    manifest = AppManifest.model_validate(persisted_snapshot)

    assert manifest.external_ingress[0].capability_id == "health-import"
    assert manifest.service.health_url == "/health"


@pytest.mark.parametrize(
    "service_path", ["/health", "/manifest", "/openapi.json", "/internal/v1/health-check"]
)
def test_service_definition_accepts_canonical_relative_paths(service_path: str) -> None:
    service = ServiceDefinition.model_validate(
        {"health_url": service_path, "manifest_url": "/manifest", "openapi_url": "/openapi.json"}
    )

    assert service.health_url == service_path


@pytest.mark.parametrize(
    "service_path",
    [
        "https://attacker.example/health",
        "//attacker.example/health",
        "health",
        "/health/",
        "/health//check",
        "/health/../admin",
        "/health?probe=1",
        "/health#fragment",
        "/health\x00",
        "/",
        "",
    ],
)
def test_service_definition_rejects_non_relative_or_unnormalized_paths(service_path: str) -> None:
    with pytest.raises(ValidationError):
        ServiceDefinition.model_validate(
            {
                "health_url": service_path,
                "manifest_url": "/manifest",
                "openapi_url": "/openapi.json",
            }
        )


# --- store listing -----------------------------------------------------------


# --- store listing -----------------------------------------------------------


def test_manifest_points_at_its_listing_rather_than_embedding_it() -> None:
    """The manifest is snapshotted and hashed at registration, and never edited.

    That immutability exists for the permission grant: an app must not be able to
    widen what it asked for after a user consented. Presentation has no such
    requirement — a screenshot is not a promise — so embedding it would force a
    republished version for a change of decoration. The manifest freezes WHERE
    the listing lives; the document it names stays editable.
    """
    data = manifest_data()
    data["store_listing_path"] = "fitness/store.json"

    manifest = AppManifest.model_validate(data)

    assert manifest.store_listing_path == "fitness/store.json"
    assert not hasattr(manifest, "store")


@pytest.mark.parametrize(
    "listing_path",
    [
        "https://cdn.example/store.json",
        "//cdn.example/store.json",
        "/fitness/store.json",
        "../../etc/passwd",
        "fitness/../../evil.json",
        "fitness/store.json?v=2",
        "",
    ],
)
def test_store_listing_path_cannot_escape_the_media_root(listing_path: str) -> None:
    data = manifest_data()
    data["store_listing_path"] = listing_path

    with pytest.raises(ValidationError):
        AppManifest.model_validate(data)


def test_store_listing_is_the_schema_of_the_external_document() -> None:
    """Validated where it is fetched, not where it is referenced."""
    listing = StoreListing.model_validate(store_listing())

    assert listing.category is AppCategory.HEALTH_AND_FITNESS
    assert listing.icon_path == "fitness/0.1.0/icon.png"
    assert len(listing.screenshots) == 2
    assert listing.screenshots[0].caption == "Today"
    assert listing.screenshots[1].caption is None


def test_asset_paths_are_relative_so_the_host_is_not_baked_into_the_manifest() -> None:
    """Where the assets are hosted is a deployment binding, like the upstream
    address was before 0.3.0 removed it.

    Baking a hostname in means a publisher cannot move their media without
    republishing every version, and every already-registered snapshot keeps
    pointing at the old host — snapshots are immutable, so those links die.
    The manifest says WHICH asset; the registry says WHERE it is served from.
    """
    listing = StoreListing.model_validate(store_listing())

    assert not str(listing.icon_path).startswith("http")
    assert not str(listing.icon_path).startswith("/")


@pytest.mark.parametrize(
    "asset_path",
    [
        "icon.png",
        "fitness/0.1.0/icon.png",
        "a/b/c/shot-1.png",
        "fitness/0.1.0/screen_1.png",
    ],
)
def test_store_listing_accepts_relative_asset_paths(asset_path: str) -> None:
    listing = StoreListing.model_validate(store_listing(icon_path=asset_path))

    assert listing.icon_path == asset_path


@pytest.mark.parametrize(
    "asset_path",
    [
        "https://cdn.example/icon.png",
        "http://cdn.example/icon.png",
        "//cdn.example/icon.png",
        "/fitness/icon.png",
        "../../etc/passwd",
        "fitness/../../etc/passwd",
        "fitness//icon.png",
        "fitness/./icon.png",
        "fitness/%2e%2e/icon.png",
        "fitness\\icon.png",
        "fitness/icon.png?v=2",
        "fitness/icon.png#frag",
        "fitness/icon.png\n",
        "fitness/icon.png\x00",
        "fitness/",
        "",
        "   ",
    ],
)
def test_store_listing_rejects_paths_that_could_escape_the_media_root(
    asset_path: str,
) -> None:
    """These are joined onto a base URL the manifest does not control.

    A value carrying a scheme, an authority, or traversal would resolve
    somewhere other than the publisher's media root — in the worst case an
    attacker-controlled host serving content under the platform's own store UI.
    """
    with pytest.raises(ValidationError):
        StoreListing.model_validate(store_listing(icon_path=asset_path))

    with pytest.raises(ValidationError):
        StoreListing.model_validate(store_listing(screenshots=[{"path": asset_path}]))


def test_publisher_links_stay_absolute_because_they_are_not_platform_assets() -> None:
    """A publisher's website is not served from the media root and does not
    move when their asset hosting does, so it stays a full URL."""
    listing = StoreListing.model_validate(store_listing())

    assert str(listing.website_url) == "https://meshflow.example/fitness"


@pytest.mark.parametrize("link_url", ["http://meshflow.example", "ftp://x.example", "/relative"])
def test_publisher_links_must_still_be_https(link_url: str) -> None:
    with pytest.raises(ValidationError):
        StoreListing.model_validate(store_listing(website_url=link_url))


def test_store_listing_serializes_paths_as_plain_strings() -> None:
    dump = StoreListing.model_validate(store_listing()).model_dump()

    assert dump["icon_path"] == "fitness/0.1.0/icon.png"
    assert dump["category"] == "health-and-fitness"
    assert dump["screenshots"][0]["path"] == "fitness/0.1.0/1.png"
    assert dump == json.loads(StoreListing.model_validate(store_listing()).model_dump_json())


def test_store_listing_rejects_duplicate_screenshot_paths() -> None:
    duplicate = {"path": "fitness/0.1.0/1.png"}

    with pytest.raises(ValidationError):
        StoreListing.model_validate(store_listing(screenshots=[duplicate, duplicate]))


def test_store_listing_rejects_too_many_screenshots() -> None:
    screenshots = [{"path": f"fitness/0.1.0/{index}.png"} for index in range(11)]

    with pytest.raises(ValidationError):
        StoreListing.model_validate(store_listing(screenshots=screenshots))


@pytest.mark.parametrize(
    "listing_overrides",
    [
        {"category": "Health And Fitness"},
        {"category": "not-a-category"},
        {"category": ""},
        {"long_description": ""},
        {"long_description": "x" * 4001},
        {"screenshots": [{"path": "fitness/1.png", "caption": "x" * 141}]},
    ],
)
def test_store_listing_rejects_invalid_values(listing_overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StoreListing.model_validate(store_listing(**listing_overrides))


@pytest.mark.parametrize("missing_field", ["long_description", "category", "icon_path"])
def test_store_listing_requires_core_presentation_fields(missing_field: str) -> None:
    listing = store_listing()
    del listing[missing_field]

    with pytest.raises(ValidationError):
        StoreListing.model_validate(listing)


def test_store_listing_optional_links_default_to_none() -> None:
    listing = StoreListing.model_validate(
        {
            "long_description": "Minimal listing.",
            "category": "utilities",
            "icon_path": "utilities/1.0.0/icon.png",
        }
    )

    assert listing.screenshots == ()
    assert listing.website_url is None
    assert listing.support_url is None
    assert listing.privacy_policy_url is None


def test_store_listing_is_immutable() -> None:
    listing = StoreListing.model_validate(store_listing())

    with pytest.raises(ValidationError):
        setattr(listing, "category", AppCategory.OTHER)


def test_store_screenshot_is_immutable() -> None:
    screenshot = StoreScreenshot.model_validate({"path": "fitness/1.png"})

    with pytest.raises(ValidationError):
        setattr(screenshot, "caption", "changed")


def test_validated_screenshots_collection_cannot_be_mutated() -> None:
    listing = StoreListing.model_validate(store_listing())

    assert not hasattr(listing.screenshots, "append")
    mutable_screenshots: Any = listing.screenshots
    with pytest.raises(TypeError):
        mutable_screenshots[0] = None


def test_app_category_values_are_stable_slugs() -> None:
    assert {category.value for category in AppCategory} == {
        "developer-tools",
        "education",
        "finance",
        "health-and-fitness",
        "lifestyle",
        "other",
        "productivity",
        "utilities",
    }


# --- release notes -----------------------------------------------------------


def test_manifest_accepts_release_notes() -> None:
    data = manifest_data()
    data["release_notes"] = "Adds recurring transactions."

    manifest = AppManifest.model_validate(data)

    assert manifest.release_notes == "Adds recurring transactions."


@pytest.mark.parametrize("release_notes", ["", "x" * 2001])
def test_manifest_rejects_invalid_release_notes(release_notes: str) -> None:
    data = manifest_data()
    data["release_notes"] = release_notes

    with pytest.raises(ValidationError):
        AppManifest.model_validate(data)
