"""Object-level authorization rules for consultations and cross-checks."""

# This file contains the main object-level access rules used to protect consultation
# data in MediExplain+. It checks whether a user is the treating doctor, the patient
# linked to a released consultation, an assigned cross-check reviewer, or an
# administrator before allowing access. It also keeps ownership checks separate for
# doctor and patient actions and treats release as a lasting boundary so a case stays
# accessible to the patient even if its later cross-check status changes.


from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Consultation, CrossCheck, User, UserRole

REVIEW_ACTIVE = {"pending", "in_review", "completed"}

async def assigned_reviewer(
    db: AsyncSession, consultation_id: int, user_id: int
) -> bool:
    res = await db.execute(
        select(CrossCheck.id).where(
            CrossCheck.consultation_id == consultation_id,
            CrossCheck.reviewer_id == user_id,
            CrossCheck.request_status.in_(REVIEW_ACTIVE),
        )
    )
    return res.scalar_one_or_none() is not None

def has_been_released(c: Consultation) -> bool:
    """Release is a durable boundary even while a later cross-check changes status."""
    return c.released_at is not None

async def require_can_view_consultation(
    db: AsyncSession, user: User, c: Consultation
) -> None:
    if user.role == UserRole.ADMIN:
        return
    if user.role == UserRole.PATIENT:
        if c.patient_id == user.id and has_been_released(c):
            return
    elif user.role == UserRole.DOCTOR:
        if c.doctor_id == user.id:
            return
        if await assigned_reviewer(db, c.id, user.id):
            return
    elif user.role == UserRole.CROSS_CHECK_DOCTOR:
        if await assigned_reviewer(db, c.id, user.id):
            return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this consultation")

def require_owner_doctor(user: User, c: Consultation) -> None:
    if user.role == UserRole.ADMIN:
        return
    if user.role == UserRole.DOCTOR and c.doctor_id == user.id:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Treating doctor access required")

def require_patient_owner(user: User, c: Consultation) -> None:
    if user.role == UserRole.ADMIN:
        return
    if user.role == UserRole.PATIENT and c.patient_id == user.id:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Patient access required")

def require_released(c: Consultation) -> None:
    if not has_been_released(c):
        raise HTTPException(status.HTTP_409_CONFLICT, "Consultation has not been released")
