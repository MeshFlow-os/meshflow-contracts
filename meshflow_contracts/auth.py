import re
from typing import Any, Literal, Mapping, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


WorkspaceRole = Literal["owner", "admin", "member"]
InstallationRole = Literal["admin", "member", "viewer"]
InternalTokenType = Literal["app_request", "lifecycle", "integration_request"]
IntegrationRequestTokenType = Literal["integration_request"]

IDENTIFIER_PATTERN = r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*$"
JWT_STRING_OR_URI_PATTERN = r"^[^\x00-\x1f\x7f]+$"
JWT_OPAQUE_URL_SAFE_PATTERN = r"^[A-Za-z0-9._~:-]+$"
MAX_INTEGRATION_REQUEST_LIFETIME_SECONDS = 3_600
MAX_JWT_REGISTERED_CLAIM_LENGTH = 512


class AuthContext(BaseModel):
    user_id: str
    workspace_id: str
    installation_id: str | None = None
    workspace_role: WorkspaceRole
    installation_role: InstallationRole | None = None
    request_id: str


class InternalJWTClaims(BaseModel):
    iss: str
    aud: str
    sub: str
    user_id: str
    workspace_id: str
    installation_id: str | None = None
    workspace_role: WorkspaceRole
    installation_role: InstallationRole | None = None
    request_id: str
    token_type: InternalTokenType
    iat: int
    exp: int
    purpose: str | None = Field(default=None)


class IntegrationRequestClaims(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    iss: str
    aud: str = Field(pattern=IDENTIFIER_PATTERN)
    sub: str
    token_type: IntegrationRequestTokenType
    workspace_id: str = Field(pattern=IDENTIFIER_PATTERN)
    installation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    app_id: str = Field(pattern=IDENTIFIER_PATTERN)
    capability_id: str = Field(pattern=IDENTIFIER_PATTERN)
    integration_grant_id: str = Field(pattern=IDENTIFIER_PATTERN)
    subject_user_id: str = Field(pattern=IDENTIFIER_PATTERN)
    scopes: tuple[str, ...] = Field(min_length=1)
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    jti: str
    iat: int = Field(strict=True)
    exp: int = Field(strict=True)

    @field_validator("iss")
    @classmethod
    def validate_string_or_uri_claim(cls, value: str) -> str:
        if len(value) > MAX_JWT_REGISTERED_CLAIM_LENGTH:
            raise ValueError("claim is too long")
        if re.fullmatch(JWT_STRING_OR_URI_PATTERN, value) is None:
            raise ValueError("claim must be a non-empty StringOrURI without control characters")
        return value

    @field_validator("sub", "jti")
    @classmethod
    def validate_opaque_url_safe_claim(cls, value: str) -> str:
        if len(value) > MAX_JWT_REGISTERED_CLAIM_LENGTH:
            raise ValueError("claim is too long")
        if re.fullmatch(JWT_OPAQUE_URL_SAFE_PATTERN, value) is None:
            raise ValueError("claim must be a non-empty URL-safe opaque string")
        return value

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, scopes: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(scopes)) != len(scopes):
            raise ValueError("scopes must be unique")
        if any(re.fullmatch(IDENTIFIER_PATTERN, scope) is None for scope in scopes):
            raise ValueError("scopes must be identifiers")
        return scopes

    @field_serializer("scopes")
    def serialize_scopes(self, value: tuple[str, ...]) -> list[str]:
        return list(value)

    @model_validator(mode="after")
    def validate_cross_field_invariants(self) -> "IntegrationRequestClaims":
        if self.aud != self.app_id:
            raise ValueError("audience must match app id")
        lifetime_seconds = self.exp - self.iat
        if lifetime_seconds <= 0 or lifetime_seconds > MAX_INTEGRATION_REQUEST_LIFETIME_SECONDS:
            raise ValueError("integration request lifetime must be positive and bounded")
        return self

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        copied = super().model_copy(deep=deep)
        data = copied.model_dump(round_trip=True)
        if update is not None:
            data.update(update)
        return type(self).model_validate(data)
