from typing import Any

from pydantic import BaseModel, Field, HttpUrl


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
