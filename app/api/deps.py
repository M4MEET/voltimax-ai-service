from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.api.middleware.jwt_auth import validate_jwt
from app.config import get_config


async def get_current_user(authorization: str = Header(None)) -> dict:
    """Extract and validate JWT from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme. Use: Bearer <token>",
        )

    return validate_jwt(token)


async def verify_dashboard_auth(x_dashboard_key: str = Header(None)) -> None:
    """Key-based auth for the analytics dashboard API."""
    import os
    expected = os.getenv("VOLTIMAX_DASHBOARD_KEY") or get_config().shopware.api_key

    if not x_dashboard_key or x_dashboard_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid dashboard key",
        )


async def verify_plugin_auth(x_api_key: str = Header(None)) -> None:
    """Auth for Server A → Server B plugin callbacks (session/message/feedback/rating/end).
    Server A sends the shared API key in the X-Api-Key header."""
    config = get_config()
    if not x_api_key or x_api_key != config.shopware.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
