"""
backend/app/core/security.py

Password hashing and JWT-based bearer token authentication.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.core.config import settings

# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


# --------------------------------------------------------------------------- #
# JWT token creation & validation
# --------------------------------------------------------------------------- #

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


class TokenPayload(BaseModel):
    sub: str  # subject, typically user id or email
    exp: datetime


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """
    Create a signed JWT access token for the given subject
    (usually a user ID or username).
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode: dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT. Raises HTTPException(401) on any
    failure (expired, malformed, bad signature).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        subject: str | None = payload.get("sub")
        if subject is None:
            raise credentials_exception
        return TokenPayload(sub=subject, exp=payload.get("exp"))
    except JWTError:
        raise credentials_exception


async def get_current_subject(token: str = Depends(oauth2_scheme)) -> str:
    """
    FastAPI dependency — extracts and validates the bearer token,
    returning the token's subject (e.g. user id).

    Usage:
        @router.get("/me")
        async def read_current_user(user_id: str = Depends(get_current_subject)):
            ...
    """
    token_data = decode_access_token(token)
    return token_data.sub