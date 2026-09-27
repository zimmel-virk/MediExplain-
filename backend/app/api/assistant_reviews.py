"""Delegated clinical-assistant pre-review.

This is additive to the original MediExplain+ workflow.  Assistants can only
inspect explicitly assigned cases and return a checklist/notes.  They cannot
modify the clinical source, approve, release, cross-check, or access unrelated
consultations.  Final release remains the original treating-doctor gate.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models import AssistantReview, Consultation, ConsultationMedication, SafetyCheck, User, UserRole
from app.schemas import (
    AssistantReviewCase, AssistantReviewCreate, AssistantReviewPublic,
    AssistantReviewSubmit,
)

# All assistant pre-review endpoints are kept under a separate API route.
router = APIRouter(prefix="/api/assistant-reviews", tags=["assistant-review"])


# Retrieves a consultation by its ID and returns a clear error if it does not exist.
async def _consultation(db: AsyncSession, cid: int) -> Consultation:
    c = (await db.execute(select(Consultation).where(Consultation.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")
    return c


# Retrieves an individual assistant review so the same lookup logic can be reused by each route.
async def _review(db: AsyncSession, rid: int) -> AssistantReview:
    r = (await db.execute(select(AssistantReview).where(AssistantReview.id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assistant review not found")
    return r


# Allows the treating doctor or an administrator to send an eligible case for assistant pre-review.
@router.post("/assign", response_model=AssistantReviewPublic, status_code=201)
async def assign_review(
    body: AssistantReviewCreate,
    db: AsyncSession = Depends(get_db),
    doctor: User = Depends(require_role(UserRole.DOCTOR, UserRole.ADMIN)),
):
    c = await _consultation(db, body.consultation_id)

    # A doctor can only delegate their own consultation, while administrators retain wider access.
    if doctor.role != UserRole.ADMIN and c.doctor_id != doctor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Treating doctor access required")

    # Pre-review is only available while the consultation is still awaiting final clinical approval.
    if c.released_at is not None or c.approved_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Approved/released cases cannot be delegated for pre-review")

    # The assistant needs a generated patient summary before there is anything meaningful to review.
    if not c.patient_summary_en:
        raise HTTPException(status.HTTP_409_CONFLICT, "The patient summary must be generated before assistant review")

    assistant = (await db.execute(select(User).where(User.id == body.assistant_id))).scalar_one_or_none()

    # Only active and verified assistant accounts can receive delegated clinical reviews.
    if not assistant or assistant.role != UserRole.ASSISTANT or not assistant.is_active or not assistant.is_verified:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selected user is not an active verified assistant")

    # Prevents the same consultation from being assigned to more than one pending review at a time.
    pending = (await db.execute(select(AssistantReview).where(
        AssistantReview.consultation_id == c.id,
        AssistantReview.status == "pending",
    ))).scalar_one_or_none()
    if pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "This consultation already has a pending assistant review")

    review = AssistantReview(
        consultation_id=c.id, assistant_id=assistant.id, assigned_by_id=doctor.id, status="pending"
    )
    db.add(review)
    await db.flush()

    # The assignment is recorded in the audit trail so delegated access remains traceable.
    await audit(db, doctor.id, "assistant_review.assigned", "consultation", c.id, {
        "review_id": review.id, "assistant_id": assistant.id,
    })
    return review


# Returns only the outstanding reviews assigned to the currently logged-in assistant.
@router.get("/pending", response_model=list[AssistantReviewPublic])
async def pending_reviews(
    db: AsyncSession = Depends(get_db),
    assistant: User = Depends(require_role(UserRole.ASSISTANT)),
):
    rows = await db.execute(select(AssistantReview).where(
        AssistantReview.assistant_id == assistant.id,
        AssistantReview.status == "pending",
    ).order_by(AssistantReview.assigned_at.desc()))
    return list(rows.scalars())


# Provides the latest review state for a consultation while applying role-specific access rules.
@router.get("/consultation/{cid}/latest", response_model=AssistantReviewPublic | None)
async def latest_for_consultation(
    cid: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    c = await _consultation(db, cid)
    query = select(AssistantReview).where(AssistantReview.consultation_id == cid)

    # Doctors can inspect review information only for consultations they are responsible for.
    if user.role == UserRole.DOCTOR:
        if c.doctor_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Treating doctor access required")

    # Assistants are restricted to reviews that were specifically assigned to them.
    elif user.role == UserRole.ASSISTANT:
        query = query.where(AssistantReview.assistant_id == user.id)
    elif user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorised")

    return (await db.execute(query.order_by(AssistantReview.assigned_at.desc()))).scalars().first()


# Returns the review record when the current user is directly involved in the case.
@router.get("/{review_id}", response_model=AssistantReviewPublic)
async def review_detail(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    review = await _review(db, review_id)
    c = await _consultation(db, review.consultation_id)

    # Access is limited to the assigned assistant, treating doctor or an administrator.
    allowed = (
        user.role == UserRole.ADMIN
        or (user.role == UserRole.ASSISTANT and review.assistant_id == user.id)
        or (user.role == UserRole.DOCTOR and c.doctor_id == user.id)
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorised for this review")
    return review


# Builds the read-only case view used by an assistant during pre-review.
@router.get("/{review_id}/case", response_model=AssistantReviewCase)
async def review_case(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    assistant: User = Depends(require_role(UserRole.ASSISTANT)),
):
    review = await _review(db, review_id)

    # An assistant cannot open a case that was delegated to somebody else.
    if review.assistant_id != assistant.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This case is not assigned to you")

    c = await _consultation(db, review.consultation_id)

    # Safety findings are included so the assistant can check warnings before returning the case.
    safety = list((await db.execute(select(SafetyCheck).where(
        SafetyCheck.consultation_id == c.id
    ).order_by(SafetyCheck.id))).scalars())

    # Medication records are loaded separately so the assistant can inspect the structured prescription details.
    medication_rows = list((await db.execute(select(ConsultationMedication).where(
        ConsultationMedication.consultation_id == c.id
    ).order_by(ConsultationMedication.id))).scalars())

    # Only the medication fields needed for review are exposed in the assistant case payload.
    medication_payload = [
        {
            "id": m.id,
            "raw_name": m.raw_name,
            "canonical_name": m.canonical_name,
            "generic_name": m.generic_name,
            "brand_name": m.brand_name,
            "strength": m.strength,
            "dose": m.dose,
            "dose_unit": m.dose_unit,
            "dosage_form": m.dosage_form,
            "route": m.route,
            "frequency": m.frequency,
            "timing": m.timing,
            "food_instruction": m.food_instruction,
            "duration": m.duration,
            "as_needed": bool(m.as_needed),
            "notes": m.notes,
            "doctor_confirmed": bool(m.doctor_confirmed),
        }
        for m in medication_rows
    ]

    # The response combines the review record with the clinical information needed for the checklist.
    return AssistantReviewCase(
        review=review, consultation_id=c.id, doctor_id=c.doctor_id, patient_id=c.patient_id,
        patient_language=c.patient_language, status=c.status, raw_transcript=c.raw_transcript,
        verified_transcript=c.verified_transcript, patient_summary_en=c.patient_summary_en,
        patient_summary_translated=c.patient_summary_translated,
        doctor_edited_summary=c.doctor_edited_summary, structured_data=c.structured_data,
        medication_rows=medication_payload, safety_checks=safety,
    )


# Completes the assistant stage and returns the reviewed case to the doctor.
@router.post("/{review_id}/submit", response_model=AssistantReviewPublic)
async def submit_review(
    review_id: int, body: AssistantReviewSubmit,
    db: AsyncSession = Depends(get_db),
    assistant: User = Depends(require_role(UserRole.ASSISTANT)),
):
    review = await _review(db, review_id)

    # Only the assistant assigned to the review can submit its checklist.
    if review.assistant_id != assistant.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This review is not assigned to you")

    # Completed reviews cannot be submitted a second time.
    if review.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Review is already completed")

    if not body.checked:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select 'I have checked this case' before returning it")

    # Every part of the pre-review checklist must be completed before the case is returned.
    required = {"transcript", "patient_summary", "medications", "warnings", "translation"}
    missing = sorted(k for k in required if not body.checklist.get(k, False))
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete the checklist first: " + ", ".join(missing))

    # Store the completed checklist, notes and completion time as the final assistant review record.
    review.checked = True
    review.checklist = body.checklist
    review.notes = body.notes
    review.status = "reviewed"
    review.checked_at = datetime.utcnow()

    # Completion is also written to the audit trail before the doctor continues the workflow.
    await audit(db, assistant.id, "assistant_review.completed", "consultation", review.consultation_id, {
        "review_id": review.id, "checked": True,
    })
    return review