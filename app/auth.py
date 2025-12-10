import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=True)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{name} is not configured",
        )
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _create_token(
    payload: Dict[str, Any], expires_delta: timedelta, secret: str, token_type: str
) -> str:
    to_encode = payload.copy()
    expires_at = _now() + expires_delta
    to_encode.update({"exp": expires_at, "iat": _now(), "type": token_type})
    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)


def create_access_token(username: str) -> str:
    expires_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    secret = _require_env("ACCESS_TOKEN_SECRET")
    return _create_token(
        {"sub": username},
        timedelta(minutes=expires_minutes),
        secret,
        token_type="access",
    )


def create_refresh_token(username: str) -> str:
    expires_days = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    secret = _require_env("REFRESH_TOKEN_SECRET")
    return _create_token(
        {"sub": username},
        timedelta(days=expires_days),
        secret,
        token_type="refresh",
    )


def decode_token(token: str, secret: str, expected_type: str) -> Dict[str, Any]:
    auth_header = {"WWW-Authenticate": "Bearer"}
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers=auth_header,
            )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers=auth_header,
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers=auth_header,
        ) from None


def verify_refresh_token(refresh_token: str) -> str:
    payload = decode_token(
        refresh_token, _require_env("REFRESH_TOKEN_SECRET"), expected_type="refresh"
    )
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    return username


def authenticate_user(username: str, password: str) -> bool:
    configured_username = os.getenv("AUTH_USERNAME")
    configured_password = os.getenv("AUTH_PASSWORD")
    if not configured_username or not configured_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AUTH_USERNAME and AUTH_PASSWORD must be set",
        )
    return secrets.compare_digest(
        username, configured_username
    ) and secrets.compare_digest(password, configured_password)


def issue_token_pair(username: str) -> Dict[str, str]:
    return {
        "access_token": create_access_token(username),
        "refresh_token": create_refresh_token(username),
        "token_type": "bearer",
    }


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    token = credentials.credentials
    payload = decode_token(
        token, _require_env("ACCESS_TOKEN_SECRET"), expected_type="access"
    )
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return username
