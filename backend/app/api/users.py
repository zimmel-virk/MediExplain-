"""/api/users — profile and verified user directories."""

# This file manages the user profile and directory endpoints used across MediExplain+.
# It lets a logged-in user retrieve their own profile, allows doctors and administrators
# to view active patient and assistant directories, and exposes the verified doctor list
# for workflows such as cross-checking. Administrators can also create new user accounts,
# with passwords stored through the existing hashing process and the creation recorded in
# the audit trail so privileged account management remains traceable.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.audit import audit
from app.core.database import get_db
from app.core.security import get_current_user, hash_password, require_role
from app.models import User, UserRole
from app.schemas import AdminUserCreate, UserPublic

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(get_current_user)):
    return user

@router.get("/patients", response_model=list[UserPublic])
async def list_patients(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.DOCTOR, UserRole.ADMIN)),
):
    res = await db.execute(
        select(User).where(User.role == UserRole.PATIENT, User.is_active.is_(True))
        .order_by(User.full_name)
    )
    return list(res.scalars())

@router.get("/assistants", response_model=list[UserPublic])
async def list_assistants(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.DOCTOR, UserRole.ADMIN)),
):
    res = await db.execute(
        select(User).where(
            User.role == UserRole.ASSISTANT,
            User.is_active.is_(True),
            User.is_verified.is_(True),
        ).order_by(User.full_name)
    )
    return list(res.scalars())


@router.get("/doctors", response_model=list[UserPublic])
async def list_doctors(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    res = await db.execute(
        select(User).where(
            User.role.in_([UserRole.DOCTOR, UserRole.CROSS_CHECK_DOCTOR]),
            User.is_active.is_(True),
            User.is_verified.is_(True),
        ).order_by(User.full_name)
    )
    return list(res.scalars())

@router.post("", response_model=UserPublic, status_code=201)
async def create_user_by_admin(
    body: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
):
    email = body.email.lower().strip()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        email=email,
        full_name=body.full_name.strip(),
        hashed_password=hash_password(body.password),
        role=body.role,
        preferred_language=body.preferred_language,
        specialty=body.specialty,
        clinic=body.clinic,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    await audit(db, admin.id, "user.created_by_admin", "user", user.id, {"role": body.role.value})
    return user
