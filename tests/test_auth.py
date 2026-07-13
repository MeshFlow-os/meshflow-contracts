import json
from importlib import import_module
from typing import Any

import pytest
from pydantic import ValidationError

import meshflow_contracts
from meshflow_contracts import IntegrationRequestClaims
from meshflow_contracts.auth import InternalJWTClaims, InternalTokenType


def integration_request_claims(**overrides: object) -> dict[str, object]:
    claims: dict[str, object] = {
        "iss": "meshflow-gateway",
        "aud": "fitness",
        "sub": "grant_public_123",
        "token_type": "integration_request",
        "workspace_id": "workspace-123",
        "installation_id": "installation-123",
        "app_id": "fitness",
        "capability_id": "health-import",
        "integration_grant_id": "grant-123",
        "subject_user_id": "user-123",
        "scopes": ["health:import", "health:write"],
        "request_id": "request-123",
        "jti": "jti-123",
        "iat": 1_700_000_000,
        "exp": 1_700_000_300,
    }
    claims.update(overrides)
    return claims


SERIALIZED_INTEGRATION_REQUEST_CLAIMS = (
    '{"iss":"meshflow-gateway","aud":"fitness","sub":"grant_public_123",'
    '"token_type":"integration_request","workspace_id":"workspace-123",'
    '"installation_id":"installation-123","app_id":"fitness",'
    '"capability_id":"health-import","integration_grant_id":"grant-123",'
    '"subject_user_id":"user-123","scopes":["health:import","health:write"],'
    '"request_id":"request-123","jti":"jti-123","iat":1700000000,"exp":1700000300}'
)

APP_REQUEST_CLAIMS: dict[str, object] = {
    "iss": "meshflow-gateway",
    "aud": "fitness",
    "sub": "user-123",
    "user_id": "user-123",
    "workspace_id": "workspace-123",
    "workspace_role": "admin",
    "request_id": "request-123",
    "token_type": "app_request",
    "iat": 1,
    "exp": 2,
}

APP_REQUEST_DUMP: dict[str, object] = {
    **APP_REQUEST_CLAIMS,
    "installation_id": None,
    "installation_role": None,
    "purpose": None,
}

LIFECYCLE_CLAIMS: dict[str, object] = {
    **APP_REQUEST_CLAIMS,
    "token_type": "lifecycle",
    "purpose": "install",
}

LIFECYCLE_DUMP: dict[str, object] = {
    **LIFECYCLE_CLAIMS,
    "installation_id": None,
    "installation_role": None,
}


def test_integration_request_claims_parse_and_serialize_safely() -> None:
    claims = IntegrationRequestClaims.model_validate(integration_request_claims())

    assert claims.token_type == "integration_request"
    assert claims.aud == "fitness"
    assert claims.app_id == "fitness"
    assert claims.scopes == ("health:import", "health:write")
    assert claims.model_dump()["scopes"] == ["health:import", "health:write"]
    assert claims.model_dump_json() == SERIALIZED_INTEGRATION_REQUEST_CLAIMS
    assert json.loads(claims.model_dump_json())["sub"] == "grant_public_123"


def test_integration_request_claims_allow_jwt_registered_claim_semantics() -> None:
    claims = IntegrationRequestClaims.model_validate(
        integration_request_claims(
            iss="https://issuer.example.com/MeshFlow",
            sub="Grant_Public-ABC_123.~",
            jti="Token-ID_ABC-123.~",
        )
    )
    human_readable_issuer_claims = IntegrationRequestClaims.model_validate(
        integration_request_claims(iss="Human Readable Issuer")
    )

    assert claims.iss == "https://issuer.example.com/MeshFlow"
    assert claims.sub == "Grant_Public-ABC_123.~"
    assert claims.jti == "Token-ID_ABC-123.~"
    assert human_readable_issuer_claims.iss == "Human Readable Issuer"


@pytest.mark.parametrize(
    "missing_claim",
    [
        "iss",
        "aud",
        "sub",
        "token_type",
        "workspace_id",
        "installation_id",
        "app_id",
        "capability_id",
        "integration_grant_id",
        "subject_user_id",
        "scopes",
        "request_id",
        "jti",
        "iat",
        "exp",
    ],
)
def test_integration_request_claims_require_all_boundary_claims(missing_claim: str) -> None:
    claims = integration_request_claims()
    claims.pop(missing_claim)

    with pytest.raises(ValidationError):
        IntegrationRequestClaims.model_validate(claims)


@pytest.mark.parametrize("token_type", ["app_request", "lifecycle", "INTEGRATION_REQUEST"])
def test_integration_request_claims_require_exact_token_type(token_type: str) -> None:
    with pytest.raises(ValidationError):
        IntegrationRequestClaims.model_validate(integration_request_claims(token_type=token_type))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("aud", "Fitness"),
        ("workspace_id", "workspace 123"),
        ("installation_id", "installation/123"),
        ("app_id", "other-app"),
        ("capability_id", "health import"),
        ("integration_grant_id", "grant/123"),
        ("subject_user_id", "user/123"),
        ("request_id", "request/123"),
    ],
)
def test_integration_request_claims_reject_invalid_identifiers(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        IntegrationRequestClaims.model_validate(integration_request_claims(**{field: value}))


@pytest.mark.parametrize(
        ("field", "value"),
        [
            ("iss", ""),
        ("iss", "issuer\nname"),
        ("iss", "issuer\x7fname"),
            ("sub", ""),
            ("sub", "subject\n123"),
        ("jti", ""),
        ("jti", "token id"),
    ],
)
def test_integration_request_claims_reject_unsafe_registered_claim_values(
    field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        IntegrationRequestClaims.model_validate(integration_request_claims(**{field: value}))


@pytest.mark.parametrize("scopes", [[], ["health:import", "health:import"], ["health import"]])
def test_integration_request_claims_reject_empty_duplicate_or_invalid_scopes(
    scopes: list[str],
) -> None:
    with pytest.raises(ValidationError):
        IntegrationRequestClaims.model_validate(integration_request_claims(scopes=scopes))


def test_integration_request_claim_scopes_are_immutable_after_validation() -> None:
    claims = IntegrationRequestClaims.model_validate(integration_request_claims())

    assert not hasattr(claims.scopes, "append")
    mutable_scopes: Any = claims.scopes
    with pytest.raises(TypeError):
        mutable_scopes[0] = "admin"


@pytest.mark.parametrize(
    "updates",
    [
        {"aud": "calendar"},
        {"exp": 1_700_000_000},
        {"scopes": []},
        {"scopes": ["health:import", "health:import"]},
        {"token_type": "app_request"},
        {"workspace_id": "Workspace"},
    ],
)
def test_integration_request_claim_copy_updates_preserve_invariants(
    updates: dict[str, object]
) -> None:
    claims = IntegrationRequestClaims.model_validate(integration_request_claims())

    with pytest.raises(ValidationError):
        claims.model_copy(update=updates)


def test_integration_request_claims_reject_undeclared_claims() -> None:
    with pytest.raises(ValidationError):
        IntegrationRequestClaims.model_validate(integration_request_claims(runtime_extension="future"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("iat", "1700000000"),
        ("iat", True),
        ("exp", "1700000300"),
        ("exp", False),
    ],
)
def test_integration_request_claims_reject_non_strict_temporal_values(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        IntegrationRequestClaims.model_validate(integration_request_claims(**{field: value}))


@pytest.mark.parametrize(
    ("iat", "exp"),
    [(1_700_000_000, 1_700_000_000), (1_700_000_300, 1_700_000_000), (1_700_000_000, 1_700_003_601)],
)
def test_integration_request_claims_reject_invalid_time_order_or_lifetime(
    iat: int, exp: int
) -> None:
    with pytest.raises(ValidationError):
        IntegrationRequestClaims.model_validate(integration_request_claims(iat=iat, exp=exp))


def test_existing_internal_jwt_claims_remain_backward_compatible() -> None:
    app_claims = InternalJWTClaims.model_validate(APP_REQUEST_CLAIMS)
    lifecycle_claims = InternalJWTClaims.model_validate(LIFECYCLE_CLAIMS)

    assert app_claims.token_type == "app_request"
    assert lifecycle_claims.token_type == "lifecycle"
    valid_token_types: set[InternalTokenType] = {"app_request", "lifecycle", "integration_request"}
    assert "integration_request" in valid_token_types


def test_legacy_internal_jwt_claim_fixtures_preserve_dump_and_json() -> None:
    app_claims = InternalJWTClaims.model_validate(APP_REQUEST_CLAIMS)
    lifecycle_claims = InternalJWTClaims.model_validate(LIFECYCLE_CLAIMS)

    assert app_claims.model_dump() == APP_REQUEST_DUMP
    assert json.loads(app_claims.model_dump_json()) == APP_REQUEST_DUMP
    assert lifecycle_claims.model_dump() == LIFECYCLE_DUMP
    assert json.loads(lifecycle_claims.model_dump_json()) == LIFECYCLE_DUMP


def test_public_import_compatibility_for_documented_modules_and_symbols() -> None:
    manifest_module = import_module("meshflow_contracts.manifest")
    auth_module = import_module("meshflow_contracts.auth")

    assert manifest_module.AppManifest.__name__ == "AppManifest"
    assert manifest_module.Publisher.__name__ == "Publisher"
    assert manifest_module.ServiceDefinition.__name__ == "ServiceDefinition"
    assert manifest_module.ExternalIngressDefinition.__name__ == "ExternalIngressDefinition"
    assert auth_module.AuthContext.__name__ == "AuthContext"
    assert auth_module.InternalJWTClaims.__name__ == "InternalJWTClaims"
    assert auth_module.IntegrationRequestClaims is IntegrationRequestClaims
    assert meshflow_contracts.__all__ == ["IntegrationRequestClaims"]


def test_public_package_exports_are_intentional() -> None:
    assert meshflow_contracts.__all__ == ["IntegrationRequestClaims"]
