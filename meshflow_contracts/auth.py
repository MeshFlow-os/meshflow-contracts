from typing import Literal

from pydantic import BaseModel, Field


WorkspaceRole = Literal["owner", "admin", "member"]
InstallationRole = Literal["admin", "member", "viewer"]
InternalTokenType = Literal["app_request", "lifecycle"]


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
