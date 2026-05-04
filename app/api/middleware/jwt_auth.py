from __future__ import annotations

import jwt
from fastapi import HTTPException, status

from app.config import get_config


def validate_jwt(token: str) -> dict:
    """Validate a JWT token issued by Server A.
    Returns the decoded claims or raises HTTPException."""
    config = get_config()

    try:
        payload = jwt.decode(
            token,
            config.jwt.secret,
            algorithms=[config.jwt.algorithm],
            options={"require": ["exp", "iat"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please re-verify.",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )

    return {
        "name": payload.get("name", ""),
        "email": payload.get("email", ""),
        "customer_id": payload.get("customer_id"),
        "has_orders": payload.get("has_orders", False),
        "is_b2b": payload.get("is_b2b", False),
        # Present when user entered an order number during verification
        "order_number": payload.get("order_number"),
        "sales_channel_id": payload.get("sales_channel_id"),
        "verified_at": payload.get("verified_at"),
    }
