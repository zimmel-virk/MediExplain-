"""/api/share — expiring, consultation-scoped read-only patient delivery."""
import asyncio,mimetypes
from fastapi import APIRouter,HTTPException,status
from fastapi.responses import FileResponse
from sqlalchemy import select
from app.core.audit import audit
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.storage import resolve_storage_ref
from app.models import Consultation,User
from app.schemas import PublicShareView
from app.services import pdf_export,share as share_svc

# This file handles the secure sharing of released MediExplain+ consultation
# summaries through temporary share links. A share token is first verified and
# mapped to its consultation, and public access is allowed only after the treating
# doctor has released the case. The shared view contains the patient-facing summary
# and structured information, while separate endpoints provide the released audio
# and generate a patient PDF when requested. Share access is also recorded in the
# audit trail so use of external consultation links remains traceable.

router=APIRouter(prefix="/api/share",tags=["share"])

async def _from_token(token:str)->Consultation:
    try:cid=share_svc.verify_share_token(token)
    except Exception as exc:raise HTTPException(status.HTTP_401_UNAUTHORIZED,"Invalid or expired link") from exc
    async with AsyncSessionLocal() as db:
        c=(await db.execute(select(Consultation).where(Consultation.id==cid))).scalar_one_or_none()
        if not c:raise HTTPException(status.HTTP_404_NOT_FOUND,"Not found")
        # Approval alone is never enough for public access.
        if c.released_at is None:raise HTTPException(status.HTTP_403_FORBIDDEN,"Not released yet")
        await audit(db,None,"share.viewed","consultation",c.id)
        await db.commit()
        await db.refresh(c)
        return c

@router.get("/{token}",response_model=PublicShareView)
async def view_shared(token:str):
    c=await _from_token(token)
    summary=c.patient_summary_translated or c.doctor_edited_summary or c.patient_summary_en or ""
    p=resolve_storage_ref(c.audio_summary_path)
    return PublicShareView(
        id=c.id,patient_language=c.patient_language,patient_summary=summary,
        structured_data=c.structured_data,has_audio=bool(p and p.exists()),has_pdf=True,
    )

@router.get("/{token}/audio")
async def shared_audio(token:str):
    c=await _from_token(token)
    p=resolve_storage_ref(c.audio_summary_path)
    if not p or not p.exists():raise HTTPException(status.HTTP_404_NOT_FOUND,"No audio available")
    return FileResponse(p,media_type=mimetypes.guess_type(p.name)[0] or "audio/wav",filename=p.name)

@router.get("/{token}/pdf")
async def shared_pdf(token:str):
    c=await _from_token(token)
    async with AsyncSessionLocal() as db:
        pat=(await db.execute(select(User).where(User.id==c.patient_id))).scalar_one()
        doc=(await db.execute(select(User).where(User.id==c.doctor_id))).scalar_one()
        schedules=await pdf_export.schedule_payload(db,c.id)
        medications=await pdf_export.medication_payload(db,c.id)
    out=settings.UPLOAD_DIR/f"share_{c.id}_{c.patient_language}.pdf"
    await asyncio.to_thread(pdf_export.generate_patient_pdf,c,pat,doc,out,schedules,medications)
    return FileResponse(out,media_type="application/pdf",filename=f"care_summary_{c.id}.pdf")
