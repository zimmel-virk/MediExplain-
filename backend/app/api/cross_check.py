"""/api/cross-check — assigned, auditable second-opinion workflow."""
from datetime import datetime
from fastapi import APIRouter,Depends,HTTPException,status
from sqlalchemy import func,select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.audit import audit
from app.core.authorization import has_been_released,require_can_view_consultation
from app.core.database import get_db
from app.core.security import get_current_user,require_role
from app.models import Consultation,ConsultationStatus,CrossCheck,User,UserRole
from app.schemas import CrossCheckCreate,CrossCheckPublic,CrossCheckSubmit

# This file manages the second-opinion workflow for consultations. It allows an
# authorised patient, treating doctor or administrator to request a review from
# another verified doctor, keeps the reviewer assignment restricted to that case,
# records the submitted verdict and comments, updates the consultation status when
# all active reviews are complete, and keeps each action traceable through auditing.
router=APIRouter(prefix="/api/cross-check",tags=["cross-check"])

@router.post("/request",response_model=CrossCheckPublic,status_code=201)
async def request_cross_check(
    body:CrossCheckCreate,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)
):
    c=(await db.execute(select(Consultation).where(Consultation.id==body.consultation_id))).scalar_one_or_none()
    if not c:raise HTTPException(status.HTTP_404_NOT_FOUND,"Consultation not found")
    if user.role==UserRole.PATIENT:
        if c.patient_id!=user.id:raise HTTPException(status.HTTP_403_FORBIDDEN,"Not your consultation")
        if not has_been_released(c):raise HTTPException(status.HTTP_409_CONFLICT,"Summary must be released first")
    elif user.role==UserRole.DOCTOR:
        if c.doctor_id!=user.id:raise HTTPException(status.HTTP_403_FORBIDDEN,"Not your consultation")
    elif user.role!=UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN,"Cannot request a cross-check")

    # The second opinion must come from a different verified clinician.
    if body.reviewer_id==c.doctor_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,"Reviewer must be different from treating doctor")
    reviewer=(await db.execute(select(User).where(User.id==body.reviewer_id))).scalar_one_or_none()
    if not reviewer or reviewer.role not in {UserRole.DOCTOR,UserRole.CROSS_CHECK_DOCTOR} or not reviewer.is_active or not reviewer.is_verified:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,"Reviewer is not a verified active doctor")
    existing=(await db.execute(select(CrossCheck).where(
        CrossCheck.consultation_id==c.id,CrossCheck.reviewer_id==reviewer.id,
        CrossCheck.request_status.in_(["pending","in_review"])
    ))).scalar_one_or_none()
    if existing:raise HTTPException(status.HTTP_409_CONFLICT,"An active request already exists for this reviewer")

    cc=CrossCheck(
        consultation_id=c.id,reviewer_id=reviewer.id,requester_id=user.id,
        request_status="pending",reason=body.reason,verdict="pending",
    )
    db.add(cc);c.status=ConsultationStatus.UNDER_CROSS_CHECK
    await db.flush()
    await audit(db,user.id,"cross_check.requested","consultation",c.id,{
        "cross_check_id":cc.id,"reviewer_id":reviewer.id,"reason":body.reason
    })
    return cc

@router.post("/{ccid}/submit",response_model=CrossCheckPublic)
async def submit_cross_check(
    ccid:int,body:CrossCheckSubmit,db:AsyncSession=Depends(get_db),
    reviewer:User=Depends(require_role(UserRole.DOCTOR,UserRole.CROSS_CHECK_DOCTOR)),
):
    cc=(await db.execute(select(CrossCheck).where(CrossCheck.id==ccid))).scalar_one_or_none()
    if not cc:raise HTTPException(status.HTTP_404_NOT_FOUND,"Cross-check not found")
    if cc.reviewer_id!=reviewer.id:raise HTTPException(status.HTTP_403_FORBIDDEN,"Not your review")
    if cc.request_status=="completed":raise HTTPException(status.HTTP_409_CONFLICT,"Review already completed")
    cc.verdict=body.verdict;cc.comments=body.comments
    cc.request_status="completed";cc.completed_at=datetime.utcnow()
    c=(await db.execute(select(Consultation).where(Consultation.id==cc.consultation_id))).scalar_one()
    pending=(await db.execute(select(func.count(CrossCheck.id)).where(
        CrossCheck.consultation_id==c.id,CrossCheck.id!=cc.id,
        CrossCheck.request_status.in_(["pending","in_review"])
    ))).scalar_one()

    # The case is marked cross-checked only when no other assigned review is still open.
    if not pending:c.status=ConsultationStatus.CROSS_CHECKED
    await audit(db,reviewer.id,"cross_check.submitted","consultation",c.id,{
        "cross_check_id":cc.id,"verdict":body.verdict
    })
    return cc

@router.get("/pending",response_model=list[CrossCheckPublic])
async def list_pending(
    db:AsyncSession=Depends(get_db),
    reviewer:User=Depends(require_role(UserRole.DOCTOR,UserRole.CROSS_CHECK_DOCTOR)),
):
    rows=(await db.execute(select(CrossCheck).where(
        CrossCheck.reviewer_id==reviewer.id,
        CrossCheck.request_status.in_(["pending","in_review"]),
    ).order_by(CrossCheck.created_at))).scalars()
    return list(rows)

@router.get("/for-consultation/{cid}",response_model=list[CrossCheckPublic])
async def list_for_consultation(
    cid:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)
):
    c=(await db.execute(select(Consultation).where(Consultation.id==cid))).scalar_one_or_none()
    if not c:raise HTTPException(status.HTTP_404_NOT_FOUND,"Consultation not found")
    await require_can_view_consultation(db,user,c)
    q=select(CrossCheck).where(CrossCheck.consultation_id==cid)

    # Reviewers only see the request assigned to them, while the consultation
    # owner and administrator can view the complete cross-check history.
    if user.id not in {c.doctor_id,c.patient_id} and user.role!=UserRole.ADMIN:
        q=q.where(CrossCheck.reviewer_id==user.id)
    rows=list((await db.execute(q.order_by(CrossCheck.created_at.desc()))).scalars())
    return rows