import re
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
INTERNAL_UPSTREAM_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9._:-]+(?:/[A-Za-z0-9._:-]+)*$")
CONTENT_TYPE_PATTERN = re.compile(r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+*-]+$")
SAFE_EXTERNAL_INGRESS_METHODS = frozenset({"GET", "POST", "PUT", "DELETE"})
MAX_EXTERNAL_INGRESS_BODY_BYTES = 100 * 1024 * 1024
MAX_EXTERNAL_INGRESS_RATE_REQUESTS = 1_000
MAX_EXTERNAL_INGRESS_RATE_WINDOW_SECONDS = 3_600


class Publisher(BaseModel):
    name: str


class ServiceDefinition(BaseModel):
    base_url: HttpUrl | str
    health_url: str
    manifest_url: str
    openapi_url: str


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
        parsed = urlsplit(path)
        segments = parsed.path.split("/")
        if (
            INTERNAL_UPSTREAM_PATH_PATTERN.fullmatch(path) is None
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
            raise ValueError("internal upstream path must be a normalized absolute path")
        return path


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

    @field_serializer("external_ingress")
    def serialize_external_ingress(
        self, value: tuple[ExternalIngressDefinition, ...]
    ) -> list[ExternalIngressDefinition]:
        return list(value)

    @model_validator(mode="after")
    def validate_unique_external_ingress_capability_ids(self) -> "AppManifest":
        capability_ids = [entry.capability_id for entry in self.external_ingress]
        if len(set(capability_ids)) != len(capability_ids):
            raise ValueError("external ingress capability ids must be unique")
        return self
