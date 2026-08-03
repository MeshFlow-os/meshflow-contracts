import re
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_serializer,
    field_validator,
    model_validator,
)


IDENTIFIER_PATTERN = r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*$"
NORMALIZED_ABSOLUTE_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9._:-]+(?:/[A-Za-z0-9._:-]+)*$")
# Kept as an alias so 0.2.x consumers importing the old name keep working.
INTERNAL_UPSTREAM_PATH_PATTERN = NORMALIZED_ABSOLUTE_PATH_PATTERN
CONTENT_TYPE_PATTERN = re.compile(r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+*-]+$")
SAFE_EXTERNAL_INGRESS_METHODS = frozenset({"GET", "POST", "PUT", "DELETE"})
MAX_EXTERNAL_INGRESS_BODY_BYTES = 100 * 1024 * 1024
MAX_EXTERNAL_INGRESS_RATE_REQUESTS = 1_000
MAX_EXTERNAL_INGRESS_RATE_WINDOW_SECONDS = 3_600
MAX_LONG_DESCRIPTION_LENGTH = 4_000
MAX_RELEASE_NOTES_LENGTH = 2_000
MAX_SCREENSHOTS = 10
MAX_SCREENSHOT_CAPTION_LENGTH = 140
MAX_ASSET_PATH_LENGTH = 512
RELATIVE_ASSET_PATH_PATTERN = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")


def validate_normalized_absolute_path(path: str) -> str:
    """Reject anything that is not a normalized, client-unroutable absolute path.

    Shared by service endpoint paths and external ingress upstream paths: both are
    concatenated onto a base URL that the manifest does not control, so a value
    carrying a scheme, an authority, traversal, or percent-encoding could redirect
    the request to an entirely different host.
    """
    parsed = urlsplit(path)
    segments = parsed.path.split("/")
    if (
        NORMALIZED_ABSOLUTE_PATH_PATTERN.fullmatch(path) is None
        or path.startswith("//")
        or path.endswith("/")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or "%" in path
        or "\\" in path
        or "" in segments[1:]
        or ".." in segments
        or "." in segments
    ):
        raise ValueError("path must be a normalized absolute path")
    return path


def validate_https_url(url: HttpUrl) -> HttpUrl:
    """Publisher links are opened in the browser, so plaintext transport is refused."""
    if url.scheme != "https":
        raise ValueError("url must use https")
    return url


def validate_relative_asset_path(path: str) -> str:
    """Reject anything that could resolve outside the publisher's media root.

    Asset paths are joined onto a base URL the manifest does not control, so a
    value carrying a scheme, an authority, or traversal would resolve somewhere
    else entirely — in the worst case an attacker-controlled host serving
    content inside the platform's own store UI.

    Relative rather than absolute on purpose: where the assets are hosted is a
    deployment binding, and a manifest that names a host cannot be moved without
    republishing every version, while every already-registered snapshot keeps
    pointing at the old one. Snapshots are immutable, so those links die.
    """
    if RELATIVE_ASSET_PATH_PATTERN.fullmatch(path) is None:
        raise ValueError("asset path must be a relative path within the media root")
    parsed = urlsplit(path)
    segments = path.split("/")
    if (
        path.startswith("/")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or "%" in path
        or "\\" in path
        or "" in segments
        or ".." in segments
        or "." in segments
    ):
        raise ValueError("asset path must be a relative path within the media root")
    return path


class Publisher(BaseModel):
    name: str


class ServiceDefinition(BaseModel):
    # Deliberately tolerant of unknown keys. `base_url` lived here until 0.3.0 and
    # is still present in every manifest snapshot already persisted by the registry;
    # those rows are immutable audit records hashed at write time, so they can never
    # be rewritten and must stay readable forever. Rejecting a retired field here
    # would turn historical data into a runtime failure on the read path.
    # Refusing a *newly submitted* manifest that still carries a deployment binding
    # is a registration-time policy decision, and belongs at that boundary.

    health_url: str
    manifest_url: str
    openapi_url: str

    @field_validator("health_url", "manifest_url", "openapi_url")
    @classmethod
    def validate_service_path(cls, path: str) -> str:
        return validate_normalized_absolute_path(path)


class NavigationEntry(BaseModel):
    id: str
    label: str
    path: str
    icon: str | None = None


class NavigationDefinition(BaseModel):
    entries: list[NavigationEntry]


class PermissionDefinition(BaseModel):
    id: str
    description: str


class SettingsDefinition(BaseModel):
    sections: list[dict[str, Any]] = Field(default_factory=list)


class ExternalIngressRatePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    requests: int = Field(strict=True, gt=0, le=MAX_EXTERNAL_INGRESS_RATE_REQUESTS)
    window_seconds: int = Field(
        strict=True, gt=0, le=MAX_EXTERNAL_INGRESS_RATE_WINDOW_SECONDS
    )


class ExternalIngressDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    capability_id: str = Field(pattern=IDENTIFIER_PATTERN)
    audience: str = Field(pattern=IDENTIFIER_PATTERN)
    allowed_methods: tuple[str, ...] = Field(min_length=1)
    allowed_content_types: tuple[str, ...] = Field(min_length=1)
    internal_upstream_path: str
    scopes: tuple[str, ...] = Field(min_length=1)
    max_body_bytes: int = Field(strict=True, gt=0, le=MAX_EXTERNAL_INGRESS_BODY_BYTES)
    rate_policy: ExternalIngressRatePolicy

    @field_validator("allowed_methods")
    @classmethod
    def validate_allowed_methods(cls, methods: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(methods)) != len(methods):
            raise ValueError("allowed methods must be unique")
        if any(method not in SAFE_EXTERNAL_INGRESS_METHODS for method in methods):
            raise ValueError("allowed methods must be safe uppercase HTTP methods")
        return methods

    @field_validator("allowed_content_types")
    @classmethod
    def validate_allowed_content_types(
        cls, content_types: tuple[str, ...]
    ) -> tuple[str, ...]:
        if len(set(content_types)) != len(content_types):
            raise ValueError("allowed content types must be unique")
        if any(CONTENT_TYPE_PATTERN.fullmatch(value) is None for value in content_types):
            raise ValueError("allowed content types must be media types")
        return content_types

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, scopes: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(scopes)) != len(scopes):
            raise ValueError("scopes must be unique")
        if any(re.fullmatch(IDENTIFIER_PATTERN, scope) is None for scope in scopes):
            raise ValueError("scopes must be identifiers")
        return scopes

    @field_serializer("allowed_methods", "allowed_content_types", "scopes")
    def serialize_policy_tuple(self, value: tuple[str, ...]) -> list[str]:
        return list(value)

    @field_validator("internal_upstream_path")
    @classmethod
    def validate_internal_upstream_path(cls, path: str) -> str:
        return validate_normalized_absolute_path(path)


class AppCategory(StrEnum):
    """Closed taxonomy: the store UI groups by it, so it cannot be free text."""

    DEVELOPER_TOOLS = "developer-tools"
    EDUCATION = "education"
    FINANCE = "finance"
    HEALTH_AND_FITNESS = "health-and-fitness"
    LIFESTYLE = "lifestyle"
    OTHER = "other"
    PRODUCTIVITY = "productivity"
    UTILITIES = "utilities"


class StoreScreenshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str = Field(min_length=1, max_length=MAX_ASSET_PATH_LENGTH)
    caption: str | None = Field(default=None, max_length=MAX_SCREENSHOT_CAPTION_LENGTH)

    @field_validator("path")
    @classmethod
    def validate_path(cls, path: str) -> str:
        return validate_relative_asset_path(path)


class StoreListing(BaseModel):
    """Schema of the store listing document a manifest points at.

    Lives outside the manifest, fetched from the publisher's media root, so
    changing a screenshot or a description is an upload rather than a republished
    app version. Only the path to this document is frozen into the manifest.

    Asset paths within it are relative to that same media root, which the registry
    holds and can repoint at any time. The document says WHICH asset; the registry
    says WHERE it is served from. Naming a host in either would repeat the mistake
    `service.base_url` made before 0.3.0 removed it: a publisher could not move
    their hosting without republishing, and every already-registered snapshot —
    immutable by design — would keep pointing at the old host.

    Publisher links stay absolute. A marketing site or privacy policy is not
    served from the media root and does not move when asset hosting does.
    """

    model_config = ConfigDict(frozen=True)

    long_description: str = Field(min_length=1, max_length=MAX_LONG_DESCRIPTION_LENGTH)
    category: AppCategory
    icon_path: str = Field(min_length=1, max_length=MAX_ASSET_PATH_LENGTH)
    screenshots: tuple[StoreScreenshot, ...] = Field(default_factory=tuple, max_length=MAX_SCREENSHOTS)
    website_url: HttpUrl | None = None
    support_url: HttpUrl | None = None
    privacy_policy_url: HttpUrl | None = None

    @field_validator("icon_path")
    @classmethod
    def validate_icon_path(cls, path: str) -> str:
        return validate_relative_asset_path(path)

    @field_validator("website_url", "support_url", "privacy_policy_url")
    @classmethod
    def validate_https(cls, url: HttpUrl | None) -> HttpUrl | None:
        return None if url is None else validate_https_url(url)

    @field_validator("screenshots")
    @classmethod
    def validate_unique_screenshots(
        cls, screenshots: tuple[StoreScreenshot, ...]
    ) -> tuple[StoreScreenshot, ...]:
        paths = [screenshot.path for screenshot in screenshots]
        if len(set(paths)) != len(paths):
            raise ValueError("screenshot paths must be unique")
        return screenshots

    @field_serializer("website_url", "support_url", "privacy_policy_url")
    def serialize_url(self, url: HttpUrl | None) -> str | None:
        return None if url is None else str(url)

    @field_serializer("screenshots")
    def serialize_screenshots(
        self, screenshots: tuple[StoreScreenshot, ...]
    ) -> list[StoreScreenshot]:
        return list(screenshots)


class AppManifest(BaseModel):
    schema_version: str
    app_id: str
    slug: str
    name: str
    version: str
    publisher: Publisher
    service: ServiceDefinition
    navigation: NavigationDefinition
    description: str | None = None
    permissions: list[PermissionDefinition] = Field(default_factory=list)
    settings: SettingsDefinition = Field(default_factory=SettingsDefinition)
    triggers: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    ai_tools: list[dict[str, Any]] = Field(default_factory=list)
    external_ingress: tuple[ExternalIngressDefinition, ...] = Field(
        default_factory=tuple, exclude_if=lambda value: value == ()
    )
    # A path, not the listing itself. The manifest is snapshotted and hashed at
    # registration and never edited again, because that immutability is what makes
    # a permission grant meaningful: an app must not be able to widen what it
    # asked for after a user consented. Presentation carries no such promise — a
    # screenshot is not something a user agreed to — so embedding it here would
    # force a republished version for a change of decoration. This freezes WHERE
    # the listing lives; the document it names stays editable.
    store_listing_path: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_ASSET_PATH_LENGTH,
        exclude_if=lambda value: value is None,
    )
    release_notes: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_RELEASE_NOTES_LENGTH,
        exclude_if=lambda value: value is None,
    )

    @field_serializer("external_ingress")
    def serialize_external_ingress(
        self, value: tuple[ExternalIngressDefinition, ...]
    ) -> list[ExternalIngressDefinition]:
        return list(value)

    @field_validator("store_listing_path")
    @classmethod
    def validate_store_listing_path(cls, path: str | None) -> str | None:
        return None if path is None else validate_relative_asset_path(path)

    @model_validator(mode="after")
    def validate_unique_external_ingress_capability_ids(self) -> "AppManifest":
        capability_ids = [entry.capability_id for entry in self.external_ingress]
        if len(set(capability_ids)) != len(capability_ids):
            raise ValueError("external ingress capability ids must be unique")
        return self
