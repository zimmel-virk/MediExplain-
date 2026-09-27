"""
Authentication & authorisation.

Passwords are bcrypt hashes.
Application sessions use signed JWTs.
Local authentication uses TOTP MFA before an access JWT is issued.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User, UserRole

# This file contains the main authentication and role-checking utilities used
# throughout MediExplain+. It handles bcrypt password hashing and verification,
# creates and validates signed access and MFA challenge tokens, encrypts stored
# TOTP secrets using Fernet, and loads the authenticated user from the database
# before protected API routes are allowed to continue. It also provides the
# reusable role dependency used to restrict endpoints to specific user roles.
# This module is limited to security,
# authentication, session validation and access-control checks.


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login"
)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(
    plain: str,
    hashed: str,
) -> bool:
    return pwd_context.verify(
        plain,
        hashed,
    )


def create_access_token(
    subject: str,
    role: str,
    extra: Optional[dict] = None,
) -> str:
    expire = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    payload = {
        "sub": subject,
        "role": role,
        "purpose": "access",
        "exp": expire,
    }

    if extra:
        payload.update(extra)

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALG,
    )


def create_mfa_challenge_token(
    subject: str,
    purpose: str,
    minutes: int = 10,
) -> str:
    if purpose not in {
        "mfa_setup",
        "mfa_login",
    }:
        raise ValueError(
            "Invalid MFA token purpose"
        )

    expire = (
        datetime.now(timezone.utc)
        + timedelta(minutes=minutes)
    )

    payload = {
        "sub": subject,
        "purpose": purpose,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALG,
    )


def decode_token(
    token: str,
) -> dict:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[
                settings.JWT_ALG
            ],
        )
    except JWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"Invalid token: {exc}",
        )


def _mfa_fernet() -> Fernet:
    key = (
        settings.MFA_FERNET_KEY
        or ""
    ).strip()

    if not key:
        raise RuntimeError(
            "MFA_FERNET_KEY is not configured"
        )

    try:
        return Fernet(
            key.encode("utf-8")
        )
    except Exception as exc:
        raise RuntimeError(
            "MFA_FERNET_KEY is invalid"
        ) from exc


def encrypt_mfa_secret(
    secret: str,
) -> str:
    return (
        _mfa_fernet()
        .encrypt(
            secret.encode("utf-8")
        )
        .decode("utf-8")
    )


def decrypt_mfa_secret(
    encrypted: str,
) -> str:
    try:
        return (
            _mfa_fernet()
            .decrypt(
                encrypted.encode(
                    "utf-8"
                )
            )
            .decode("utf-8")
        )
    except InvalidToken as exc:
        raise RuntimeError(
            "Stored MFA secret could not be decrypted"
        ) from exc


async def get_current_user(
    token: str = Depends(
        oauth2_scheme
    ),
    db: AsyncSession = Depends(
        get_db
    ),
) -> User:
    payload = decode_token(token)

    purpose = payload.get(
        "purpose"
    )

    if purpose in {
        "mfa_setup",
        "mfa_login",
    }:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "MFA challenge token cannot be used as an access token",
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token missing subject",
        )

    result = await db.execute(
        select(User).where(
            User.id == int(
                user_id
            )
        )
    )

    user = (
        result
        .scalar_one_or_none()
    )

    if (
        not user
        or not user.is_active
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "User not found or inactive",
        )

    return user


def require_role(
    *allowed: UserRole,
):
    async def _checker(
        user: User = Depends(
            get_current_user
        ),
    ) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                (
                    "Requires one of roles: "
                    f"{[r.value for r in allowed]}"
                ),
            )

        return user

    return _checker
