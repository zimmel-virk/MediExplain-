"""/api/auth — registration, local MFA login and Cognito exchange."""

# This file handles the main authentication flow for MediExplain+. It covers
# local account registration and login, TOTP-based MFA for normal local users,
# the demo-account login exception, Cognito token exchange, role mapping and
# the creation of application access tokens. It also keeps authentication
# activity recorded in the audit trail and checks account status, verification
# and role rules before a user is allowed into the system.

import secrets
from datetime import datetime

import pyotp
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import (
    OAuth2PasswordRequestForm,
)
from pydantic import (
    BaseModel,
    Field,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.core.audit import audit
from app.core.cognito import (
    verify_cognito_id_token,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_mfa_challenge_token,
    decode_token,
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    hash_password,
    verify_password,
)
from app.models import (
    User,
    UserRole,
)
from app.schemas import (
    Token,
    UserCreate,
    UserPublic,
)


router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


class CognitoExchangeRequest(
    BaseModel
):
    id_token: str = Field(
        min_length=20
    )
    preferred_language: str = "en"


class LocalLoginResponse(
    BaseModel
):
    status: str
    access_token: str | None = None
    token_type: str = "bearer"
    user: UserPublic | None = None
    mfa_token: str | None = None
    setup_secret: str | None = None
    otpauth_uri: str | None = None


class MfaVerifyRequest(
    BaseModel
):
    mfa_token: str = Field(
        min_length=20
    )
    code: str = Field(
        min_length=6,
        max_length=8,
    )


COGNITO_GROUP_ROLES = {
    "PATIENT":
        UserRole.PATIENT,
    "DOCTOR":
        UserRole.DOCTOR,
    "ASSISTANT":
        UserRole.ASSISTANT,
    "CROSS_CHECK_DOCTOR":
        UserRole.CROSS_CHECK_DOCTOR,
    "ADMIN":
        UserRole.ADMIN,
}


STAFF_ROLES = {
    UserRole.DOCTOR,
    UserRole.ASSISTANT,
    UserRole.CROSS_CHECK_DOCTOR,
    UserRole.ADMIN,
}


DEMO_EMAIL_SUFFIX = "@demo.com"


def _is_demo_account(user: User) -> bool:
    """Seeded assessment/demo accounts intentionally bypass local MFA."""
    return (
        str(user.email)
        .lower()
        .strip()
        .endswith(DEMO_EMAIL_SUFFIX)
    )


def _local_auth_required() -> None:
    if (
        settings.AUTH_MODE
        .lower()
        .strip()
        not in {
            "local",
            "dual",
        }
    ):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Local authentication is disabled in this deployment",
        )


def _cognito_auth_required() -> None:
    if (
        settings.AUTH_MODE
        .lower()
        .strip()
        not in {
            "cognito",
            "dual",
        }
    ):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Cognito authentication is disabled in this deployment",
        )


def _role_from_cognito_groups(
    claims: dict,
) -> UserRole:
    groups = (
        claims.get(
            "cognito:groups"
        )
        or []
    )

    if isinstance(
        groups,
        str,
    ):
        groups = [groups]

    recognised = {
        str(group).upper()
        for group in groups
        if str(group).upper()
        in COGNITO_GROUP_ROLES
    }

    if len(recognised) > 1:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Cognito account has conflicting MediExplain roles",
        )

    if not recognised:
        return UserRole.PATIENT

    group = next(
        iter(recognised)
    )

    return COGNITO_GROUP_ROLES[
        group
    ]


async def _mfa_user(
    *,
    token: str,
    expected_purpose: str,
    db: AsyncSession,
) -> User:
    payload = decode_token(token)

    if (
        payload.get("purpose")
        != expected_purpose
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired MFA challenge",
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "MFA challenge missing subject",
        )

    user = (
        await db.execute(
            select(User).where(
                User.id
                == int(user_id)
            )
        )
    ).scalar_one_or_none()

    if (
        user is None
        or not user.is_active
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Account unavailable",
        )

    return user


async def _issue_local_token(
    *,
    user: User,
    db: AsyncSession,
) -> Token:
    user.last_login_at = (
        datetime.utcnow()
    )

    token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
        extra={
            "auth_source":
                "local_mfa"
        },
    )

    await audit(
        db,
        user.id,
        "user.login",
        "user",
        user.id,
        {
            "auth_source":
                "local_mfa",
            "mfa":
                True,
        },
    )

    return Token(
        access_token=token,
        user=UserPublic.model_validate(
            user
        ),
    )


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=201,
)
async def register(
    body: UserCreate,
    db: AsyncSession = Depends(
        get_db
    ),
):
    _local_auth_required()

    email = (
        body.email
        .lower()
        .strip()
    )

    existing = await db.execute(
        select(User).where(
            User.email == email
        )
    )

    if (
        existing
        .scalar_one_or_none()
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Email already registered",
        )

    user = User(
        email=email,
        full_name=(
            body.full_name.strip()
        ),
        hashed_password=(
            hash_password(
                body.password
            )
        ),
        role=UserRole.PATIENT,
        preferred_language=(
            body.preferred_language
        ),
        is_verified=True,
        mfa_enabled=False,
    )

    db.add(user)
    await db.flush()

    await audit(
        db,
        user.id,
        "user.registered",
        "user",
        user.id,
        {
            "role":
                "patient"
        },
    )

    return user


@router.post(
    "/login",
    response_model=LocalLoginResponse,
)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(
        get_db
    ),
):
    _local_auth_required()

    email = (
        form.username
        .lower()
        .strip()
    )

    user = (
        await db.execute(
            select(User).where(
                User.email == email
            )
        )
    ).scalar_one_or_none()

    if (
        not user
        or not verify_password(
            form.password,
            user.hashed_password,
        )
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Account inactive",
        )

    if (
        user.role in STAFF_ROLES
        and not user.is_verified
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Professional account is awaiting verification",
        )

    # Seeded assessment accounts remain frictionless for
    # demonstrations. This exemption is intentionally limited
    # to the reserved @demo.com namespace. Every non-demo local
    # account continues through TOTP setup / verification.
    if _is_demo_account(user):
        user.last_login_at = datetime.utcnow()

        token = create_access_token(
            subject=str(user.id),
            role=user.role.value,
            extra={
                "auth_source": "local_demo",
                "mfa": False,
                "demo_account": True,
            },
        )

        await audit(
            db,
            user.id,
            "user.login",
            "user",
            user.id,
            {
                "auth_source": "local_demo",
                "mfa": False,
                "demo_account": True,
            },
        )

        return LocalLoginResponse(
            status="authenticated",
            access_token=token,
            user=UserPublic.model_validate(user),
        )

    if not user.mfa_enabled:
        if (
            not user
            .mfa_secret_encrypted
        ):
            secret = (
                pyotp.random_base32()
            )

            user.mfa_secret_encrypted = (
                encrypt_mfa_secret(
                    secret
                )
            )

            await db.flush()

        else:
            secret = (
                decrypt_mfa_secret(
                    user
                    .mfa_secret_encrypted
                )
            )

        challenge = (
            create_mfa_challenge_token(
                str(user.id),
                "mfa_setup",
                minutes=10,
            )
        )

        uri = (
            pyotp.TOTP(secret)
            .provisioning_uri(
                name=user.email,
                issuer_name=(
                    "MediExplain+"
                ),
            )
        )

        return LocalLoginResponse(
            status=(
                "mfa_setup_required"
            ),
            mfa_token=challenge,
            setup_secret=secret,
            otpauth_uri=uri,
        )

    challenge = (
        create_mfa_challenge_token(
            str(user.id),
            "mfa_login",
            minutes=5,
        )
    )

    return LocalLoginResponse(
        status="mfa_required",
        mfa_token=challenge,
    )


@router.post(
    "/mfa/setup/verify",
    response_model=Token,
)
async def verify_mfa_setup(
    body: MfaVerifyRequest,
    db: AsyncSession = Depends(
        get_db
    ),
):
    user = await _mfa_user(
        token=body.mfa_token,
        expected_purpose=(
            "mfa_setup"
        ),
        db=db,
    )

    if (
        not user
        .mfa_secret_encrypted
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No MFA setup is pending",
        )

    secret = decrypt_mfa_secret(
        user.mfa_secret_encrypted
    )

    valid = (
        pyotp.TOTP(secret).verify(
            body.code.strip(),
            valid_window=1,
        )
    )

    if not valid:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid authentication code",
        )

    user.mfa_enabled = True

    await audit(
        db,
        user.id,
        "user.mfa_enabled",
        "user",
        user.id,
        {
            "method":
                "totp"
        },
    )

    return await _issue_local_token(
        user=user,
        db=db,
    )


@router.post(
    "/mfa/verify",
    response_model=Token,
)
async def verify_mfa_login(
    body: MfaVerifyRequest,
    db: AsyncSession = Depends(
        get_db
    ),
):
    user = await _mfa_user(
        token=body.mfa_token,
        expected_purpose=(
            "mfa_login"
        ),
        db=db,
    )

    if (
        not user.mfa_enabled
        or not user
        .mfa_secret_encrypted
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "MFA is not enabled for this account",
        )

    secret = decrypt_mfa_secret(
        user.mfa_secret_encrypted
    )

    valid = (
        pyotp.TOTP(secret).verify(
            body.code.strip(),
            valid_window=1,
        )
    )

    if not valid:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid authentication code",
        )

    return await _issue_local_token(
        user=user,
        db=db,
    )


@router.post(
    "/cognito/exchange",
    response_model=Token,
)
async def cognito_exchange(
    body: CognitoExchangeRequest,
    db: AsyncSession = Depends(
        get_db
    ),
):
    _cognito_auth_required()

    claims = await (
        verify_cognito_id_token(
            body.id_token
        )
    )

    email = str(
        claims.get("email")
        or ""
    ).lower().strip()

    if not email:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Cognito token does not contain an email address",
        )

    email_verified = claims.get(
        "email_verified"
    )

    if email_verified not in {
        True,
        "true",
        "True",
    }:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Cognito email address is not verified",
        )

    cognito_role = (
        _role_from_cognito_groups(
            claims
        )
    )

    user = (
        await db.execute(
            select(User).where(
                User.email == email
            )
        )
    ).scalar_one_or_none()

    preferred_language = (
        body.preferred_language
    )

    if (
        preferred_language
        not in settings
        .SUPPORTED_LANGUAGES
    ):
        preferred_language = "en"

    if user is None:
        name = str(
            claims.get("name")
            or email.split(
                "@",
                1,
            )[0]
        ).strip()

        user = User(
            email=email,
            full_name=name[:255],
            hashed_password=(
                hash_password(
                    secrets
                    .token_urlsafe(48)
                )
            ),
            role=cognito_role,
            preferred_language=(
                preferred_language
            ),
            is_active=True,
            is_verified=True,
        )

        db.add(user)
        await db.flush()

        await audit(
            db,
            user.id,
            "user.cognito_linked",
            "user",
            user.id,
            {
                "role":
                    cognito_role.value,
                "cognito_sub":
                    claims.get(
                        "sub"
                    ),
            },
        )

    else:
        if not user.is_active:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Account inactive",
            )

        if (
            user.role
            in STAFF_ROLES
            and cognito_role
            == UserRole.PATIENT
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                (
                    "This professional account is not assigned "
                    "to a Cognito staff group"
                ),
            )

        if (
            cognito_role
            in STAFF_ROLES
        ):
            user.role = (
                cognito_role
            )

        elif (
            user.role
            == UserRole.PATIENT
        ):
            user.role = (
                UserRole.PATIENT
            )

        user.is_verified = True

    user.last_login_at = (
        datetime.utcnow()
    )

    token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
        extra={
            "auth_source":
                "cognito",
            "cognito_sub":
                claims.get("sub"),
        },
    )

    await audit(
        db,
        user.id,
        "user.login",
        "user",
        user.id,
        {
            "auth_source":
                "cognito",
            "role":
                user.role.value,
            "mfa_enforced_by":
                "cognito",
        },
    )

    return Token(
        access_token=token,
        user=UserPublic.model_validate(
            user
        ),
    )
