"""
Amazon Cognito verification for MediExplain+.

Cognito authenticates the user. After successful verification the auth API
maps the Cognito identity/group to the existing MediExplain User record and
issues the application's existing short-lived session JWT.

This preserves the existing object-level RBAC and consultation workflow.
"""

# This file verifies Amazon Cognito ID tokens before they are accepted by
# MediExplain+. It builds the expected Cognito issuer from the configured AWS
# region and user pool, retrieves and temporarily caches the public signing
# keys, and uses the matching key to validate the token signature, audience,
# issuer and token type. If Cognito rotates its signing keys, the key set is
# refreshed automatically before validation fails. Once the token is verified,
# its claims are returned to the authentication layer, where the Cognito
# identity can be linked to the application's existing user and role system.



import time

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.config import settings


_jwks_cache: dict | None = None
_jwks_cache_until: float = 0.0


def _issuer() -> str:
    return (
        f"https://cognito-idp.{settings.AWS_REGION}.amazonaws.com/"
        f"{settings.COGNITO_USER_POOL_ID}"
    )


async def _get_jwks(force_refresh: bool = False) -> dict:
    global _jwks_cache, _jwks_cache_until

    now = time.time()

    if (
        not force_refresh
        and _jwks_cache is not None
        and now < _jwks_cache_until
    ):
        return _jwks_cache

    url = f"{_issuer()}/.well-known/jwks.json"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            jwks = response.json()
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Unable to retrieve Cognito signing keys: {exc}",
        )

    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Invalid Cognito signing-key response",
        )

    _jwks_cache = jwks
    _jwks_cache_until = now + 3600
    return jwks


async def verify_cognito_id_token(token: str) -> dict:
    if not settings.COGNITO_USER_POOL_ID or not settings.COGNITO_CLIENT_ID:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Cognito is not configured",
        )

    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg")

        if not kid or alg != "RS256":
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Invalid Cognito token header",
            )

        jwks = await _get_jwks()
        key = next(
            (item for item in jwks["keys"] if item.get("kid") == kid),
            None,
        )

        if key is None:
            jwks = await _get_jwks(force_refresh=True)
            key = next(
                (item for item in jwks["keys"] if item.get("kid") == kid),
                None,
            )

        if key is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Cognito signing key not found",
            )

        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.COGNITO_CLIENT_ID,
            issuer=_issuer(),
            options={"verify_at_hash": False},
        )

        if payload.get("token_use") != "id":
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Expected a Cognito ID token",
            )

        return payload

    except HTTPException:
        raise
    except JWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"Invalid Cognito token: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"Cognito token validation failed: {exc}",
        )
