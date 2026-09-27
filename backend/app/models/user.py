"""User model and explicit role/verification state."""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    String,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.core.base import Base


class UserRole(
    str,
    enum.Enum,
):
    DOCTOR = "doctor"
    PATIENT = "patient"
    CROSS_CHECK_DOCTOR = (
        "cross_check_doctor"
    )
    ASSISTANT = "assistant"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    full_name: Mapped[str] = (
        mapped_column(
            String(255)
        )
    )

    hashed_password: Mapped[str] = (
        mapped_column(
            String(255)
        )
    )

    role: Mapped[UserRole] = (
        mapped_column(
            Enum(UserRole),
            default=UserRole.PATIENT,
        )
    )

    preferred_language: Mapped[str] = (
        mapped_column(
            String(8),
            default="en",
        )
    )

    specialty: Mapped[
        str | None
    ] = mapped_column(
        String(120),
        nullable=True,
    )

    clinic: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
    )

    is_active: Mapped[bool] = (
        mapped_column(
            Boolean,
            default=True,
        )
    )

    is_verified: Mapped[bool] = (
        mapped_column(
            Boolean,
            default=False,
        )
    )

    mfa_enabled: Mapped[bool] = (
        mapped_column(
            Boolean,
            default=False,
        )
    )

    mfa_secret_encrypted: Mapped[
        str | None
    ] = mapped_column(
        String(512),
        nullable=True,
    )

    last_login_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = (
        mapped_column(
            DateTime,
            server_default=func.now(),
        )
    )
