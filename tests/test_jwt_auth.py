from __future__ import annotations

import time

import jwt
import pytest
from fastapi import HTTPException

import app.config as cfg_module
from app.api.middleware.jwt_auth import validate_jwt
from app.config import AppConfig


SECRET = "test-secret-that-is-long-enough-32c"
ALG = "HS256"


def _make_config():
    cfg_module._config = AppConfig(
        shopware={"server_a_url": "http://localhost", "api_key": "test"},
        jwt={"secret": SECRET, "algorithm": ALG},
    )


def _make_token(payload: dict, secret: str = SECRET) -> str:
    return jwt.encode(payload, secret, algorithm=ALG)


def test_valid_token():
    _make_config()
    token = _make_token({
        "name": "Jane Doe",
        "email": "jane@example.com",
        "order_number": "ORD-001",
        "sales_channel_id": "sc-123",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    })

    claims = validate_jwt(token)

    assert claims["name"] == "Jane Doe"
    assert claims["email"] == "jane@example.com"
    assert claims["order_number"] == "ORD-001"
    assert claims["sales_channel_id"] == "sc-123"


def test_expired_token():
    _make_config()
    token = _make_token({
        "name": "Old User",
        "email": "old@example.com",
        "iat": int(time.time()) - 7200,
        "exp": int(time.time()) - 3600,  # expired 1 hour ago
    })

    with pytest.raises(HTTPException) as exc_info:
        validate_jwt(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_invalid_signature():
    _make_config()
    token = _make_token(
        {"name": "Hacker", "email": "hack@example.com", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        secret="wrong-secret",
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_jwt(token)
    assert exc_info.value.status_code == 401


def test_missing_exp_claim():
    _make_config()
    # No exp field — should fail because we require it
    token = _make_token({"name": "No Exp", "email": "x@y.com", "iat": int(time.time())})

    with pytest.raises(HTTPException) as exc_info:
        validate_jwt(token)
    assert exc_info.value.status_code == 401


def test_missing_iat_claim():
    _make_config()
    # No iat field — should fail because we require it
    token = _make_token({"name": "No Iat", "email": "x@y.com", "exp": int(time.time()) + 3600})

    with pytest.raises(HTTPException) as exc_info:
        validate_jwt(token)
    assert exc_info.value.status_code == 401


def test_optional_claims_default_to_none():
    _make_config()
    token = _make_token({
        "name": "Minimal User",
        "email": "min@example.com",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    })

    claims = validate_jwt(token)
    assert claims["order_number"] is None
    assert claims["sales_channel_id"] is None
    assert claims["verified_at"] is None
