"""Shared MeshFlow platform contracts."""

from meshflow_contracts.auth import IntegrationRequestClaims
from meshflow_contracts.manifest import (
    AppCategory,
    AppManifest,
    ExternalIngressDefinition,
    ExternalIngressRatePolicy,
    NavigationDefinition,
    NavigationEntry,
    PermissionDefinition,
    Publisher,
    ServiceDefinition,
    SettingsDefinition,
    StoreListing,
    StoreScreenshot,
)

__version__ = "0.3.0"

__all__ = [
    "AppCategory",
    "AppManifest",
    "ExternalIngressDefinition",
    "ExternalIngressRatePolicy",
    "IntegrationRequestClaims",
    "NavigationDefinition",
    "NavigationEntry",
    "PermissionDefinition",
    "Publisher",
    "ServiceDefinition",
    "SettingsDefinition",
    "StoreListing",
    "StoreScreenshot",
]
