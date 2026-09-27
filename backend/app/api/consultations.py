"""/api/consultations — integrated consultation lifecycle."""
# This file manages the complete consultation lifecycle used by MediExplain+. It starts with\n"
# consent and consultation creation, accepts consultation audio and runs the AI processing\n"
# pipeline, then stores the transcript, summaries, safety checks and medication information\n"
# needed for clinical review. Doctors can review or correct transcript segments, regenerate\n"
# downstream outputs, reconcile prescription OCR results and confirm medication instructions.\n"
# The approval flow makes sure assistant review, safety warnings, medication schedules,\n"
# translation checks and patient-facing audio are completed before the case is approved and\n"
# released. The same API also controls role-based access, cross-checking, patient downloads,\n"
# PDF/WhatsApp/share delivery, consent withdrawal, deletion and the audit trail around these\n"
# actions so that the patient only receives the final reviewed information.\n"

from __future__ import annotations
import asyncio, hashlib, json, logging, mimetypes, shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession


from app.core.audit import audit
from app.core.authorization import (
    has_been_released, require_can_view_consultation, require_owner_doctor,
    require_patient_owner, require_released,
)
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.security import get_current_user
from app.core.storage import resolve_storage_ref, safe_unlink, to_storage_ref
from app.models import (
    AssistantReview, AuditLog, ConsentRecord, Consultation, ConsultationMedication,
    ConsultationStatus, CrossCheck, MedicationConcept, MedicationEvent,
    MedicationSchedule, Prescription, SafetyCheck, SummaryVersion,
    TranscriptSegment, TranslationRecord, User, UserRole,
)
from app.schemas import (
    ConsultationCreate, ConsultationPublic, DoctorApproval, MedicationUpdate,
    OCRCorrection, OCRResult, SafetyCheckPublic, ShareLink,
    TranscriptSegmentPublic, TranscriptSegmentUpdate,
)
from app.services import (
    ocr as ocr_svc, pdf_export, share as share_svc, translation, tts, whatsapp as whatsapp_svc,
)
from app.services import medication_index, scheduler
from app.services.orchestrator import process_consultation

from zoneinfo import ZoneInfo

logger=logging.getLogger(__name__)
router=APIRouter(prefix="/api/consultations",tags=["consultations"])


def _api_view(user: User, c: Consultation):
    view=ConsultationPublic.model_validate(c)
    if user.role==UserRole.PATIENT:
        return view.model_copy(update={
            "raw_transcript":None,"transcript_normalised":None,"verified_transcript":None,
            "clinical_note":None,"pipeline_error":None,"model_metadata":None,
            "dose_sentences_for_review":None,
        })
    return view

async def _load(db:AsyncSession,cid:int)->Consultation:
    c=(await db.execute(select(Consultation).where(Consultation.id==cid))).scalar_one_or_none()
    if not c: raise HTTPException(status.HTTP_404_NOT_FOUND,"Consultation not found")
    return c


def _require_clinical_editable(c: Consultation) -> None:
    """Clinical source data is locked after doctor approval."""
    if c.approved_at is not None or c.status in {
        ConsultationStatus.APPROVED,
        ConsultationStatus.RELEASED,
        ConsultationStatus.UNDER_CROSS_CHECK,
        ConsultationStatus.CROSS_CHECKED,
    }:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Approved/released clinical data is immutable. Create a new version/case for corrections.",
        )

def _legacy_med_list(c:Consultation)->list[dict]:
    data=dict(c.structured_data or {})
    meds=list(data.get("medications") or [])
    return meds

def _set_legacy_meds(c:Consultation,meds:list[dict]):
    data=dict(c.structured_data or {})
    data["medications"]=meds
    c.structured_data=data

async def _confirmed_medication_rows(
    db: AsyncSession,
    consultation_id: int,
) -> list[ConsultationMedication]:
    return list(
        (
            await db.execute(
                select(ConsultationMedication)
                .where(
                    ConsultationMedication.consultation_id
                    == consultation_id
                )
                .order_by(
                    ConsultationMedication.source_index,
                    ConsultationMedication.id,
                )
            )
        ).scalars()
    )


def _med_row_to_structured(
    med: ConsultationMedication,
) -> dict:
    return {
        "name": med.canonical_name or med.raw_name or "",
        "name_as_heard": med.raw_name or "",
        "canonical_name": med.canonical_name,
        "generic_name": med.generic_name,
        "brand_name": med.brand_name,
        "concept_id": med.concept_id,
        "strength": med.strength,
        "dose": med.dose,
        "dose_unit": med.dose_unit,
        "dosage_form": med.dosage_form,
        "route": med.route,
        "frequency": med.frequency,
        "timing": med.timing,
        "food_instruction": med.food_instruction,
        "duration": med.duration,
        "as_needed": bool(med.as_needed),
        "indication": med.indication,
        "notes": med.notes,
        "confidence": med.extraction_confidence,
        "match_confidence": med.match_confidence,
        "doctor_confirmed": bool(med.doctor_confirmed),
        "source": med.source,
    }


async def _sync_confirmed_medications(
    db: AsyncSession,
    c: Consultation,
) -> list[ConsultationMedication]:
    rows = await _confirmed_medication_rows(db, c.id)

    confirmed = [
        row for row in rows
        if row.doctor_confirmed
    ]

    data = dict(c.structured_data or {})
    data["medications"] = [
        _med_row_to_structured(row)
        for row in confirmed
    ]

    c.structured_data = data

    return confirmed


def _validate_medication_schedule(
    med: ConsultationMedication,
) -> str | None:
    parsed = scheduler.parse_frequency(
        med.frequency
    )

    if med.as_needed or parsed.get("kind") == "prn":
        return None

    if not med.frequency:
        return "frequency is missing"

    if not parsed.get("supported"):
        return (
            parsed.get("reason")
            or "frequency could not be interpreted"
        )

    start = (
        med.start_date
        or datetime.now(
            ZoneInfo(settings.DEFAULT_TIMEZONE)
        ).date()
    )

    end = (
        med.end_date
        or scheduler.parse_duration(
            med.duration,
            start,
        )
    )

    if end is None:
        return "duration/end date is missing"

    events, reason = scheduler.build_events(
        med.frequency,
        start,
        end,
        settings.DEFAULT_TIMEZONE,
    )

    if reason:
        return reason

    if not events:
        return "no reminder times could be generated"

    return None

async def _save_pipeline_rows(
    db: AsyncSession,
    c: Consultation,
    outcome: dict,
    replace_transcript_segments: bool = True,
) -> None:
    """
    Save AI-generated consultation artifacts.

    Normal first pipeline run:
        replace_transcript_segments=True
        -> generated STT segments are stored.

    Regeneration after doctor transcript review:
        replace_transcript_segments=False
        -> doctor-reviewed TranscriptSegment rows are preserved,
           while downstream AI outputs are regenerated.
    """

    # ---------------------------------------------------------
    # 1. TRANSCRIPT SEGMENTS
    # ---------------------------------------------------------
    # Only delete/recreate transcript segments during a normal
    # audio -> STT pipeline run.
    #
    # During regeneration from verified_transcript  MUST keep
    # the doctor's reviewed segment corrections.
    if replace_transcript_segments:
        await db.execute(
            delete(TranscriptSegment).where(
                TranscriptSegment.consultation_id == c.id
            )
        )

    # ---------------------------------------------------------
    # 2. OLD SAFETY CHECKS
    # ---------------------------------------------------------
    # Safety checks depend on the clinical source/summary.
    # Therefore they must be regenerated when the transcript changes.
    await db.execute(
        delete(SafetyCheck).where(
            SafetyCheck.consultation_id == c.id
        )
    )

    # ---------------------------------------------------------
    # 3. OLD AI-EXTRACTED MEDICATION ROWS
    # ---------------------------------------------------------
    # Replace transcript/pipeline-generated medication rows.
    #
    # Prescription rows are deliberately NOT deleted here.
    await db.execute(
        delete(ConsultationMedication).where(
            ConsultationMedication.consultation_id == c.id,
            ConsultationMedication.source.in_(
                ["transcript", "pipeline"]
            ),
        )
    )

    # ---------------------------------------------------------
    # 4. SAVE TRANSCRIPT SEGMENTS
    # ---------------------------------------------------------
    if replace_transcript_segments:
        for i, s in enumerate(
            outcome.get("transcript_segments") or []
        ):
            db.add(
                TranscriptSegment(
                    consultation_id=c.id,
                    segment_index=i,
                    start_seconds=float(
                        s.get("start", 0)
                    ),
                    end_seconds=float(
                        s.get("end", 0)
                    ),
                    text_raw=s.get("text") or "",
                    language=s.get("language"),
                    language_confidence=s.get(
                        "language_confidence"
                    ),
                    avg_logprob=s.get(
                        "avg_logprob"
                    ),
                    no_speech_prob=s.get(
                        "no_speech_prob"
                    ),
                    confidence=s.get(
                        "confidence"
                    ),
                    speaker_label=s.get(
                        "speaker"
                    ),
                    diarization_confidence=s.get(
                        "diarization_confidence"
                    ),
                    needs_review=bool(
                        s.get("needs_review")
                    ),
                )
            )

    # ---------------------------------------------------------
    # 5. SAVE NEW SAFETY CHECKS
    # ---------------------------------------------------------
    for chk in outcome.get("safety_checks") or []:
        db.add(
            SafetyCheck(
                consultation_id=c.id,
                check_type=chk.get(
                    "check_type",
                    "unknown",
                ),
                status=chk.get(
                    "status",
                    "warning",
                ),
                severity=chk.get(
                    "severity",
                    "medium",
                ),
                statement=chk.get(
                    "statement"
                ),
                evidence=chk.get(
                    "evidence"
                ),
                score=chk.get(
                    "score"
                ),
                details=chk.get(
                    "details"
                ),
                resolved=bool(
                    chk.get(
                        "resolved",
                        False,
                    )
                ),
            )
        )

    # ---------------------------------------------------------
    # 6. SAVE NEW AI-EXTRACTED MEDICATIONS
    # ---------------------------------------------------------
    structured = (
        outcome.get("structured_data")
        or {}
    )

    medications = (
        structured.get("medications")
        or []
    )

    for i, m in enumerate(medications):
        suggestions = (
            m.get("suggestions")
            or []
        )

        top = (
            suggestions[0]
            if suggestions
            else {}
        )

        db.add(
            ConsultationMedication(
                consultation_id=c.id,
                source="transcript",
                source_index=i,

                raw_name=(
                    m.get("name_as_heard")
                    or m.get("name")
                ),

                concept_id=top.get(
                    "concept_id"
                ),

                canonical_name=(
                    top.get("display_name")
                    or m.get("name")
                ),

                generic_name=top.get(
                    "generic_name"
                ),

                brand_name=top.get(
                    "brand_name"
                ),

                strength=(
                    m.get("strength")
                    or top.get("strength")
                ),

                dose=m.get(
                    "dose"
                ),

                dose_unit=m.get(
                    "dose_unit"
                ),

                dosage_form=(
                    m.get("dosage_form")
                    or top.get("dosage_form")
                ),

                route=(
                    m.get("route")
                    or top.get("route")
                ),

                frequency=m.get(
                    "frequency"
                ),

                timing=m.get(
                    "timing"
                ),

                food_instruction=m.get(
                    "food_instruction"
                ),

                duration=m.get(
                    "duration"
                ),

                as_needed=bool(
                    m.get("as_needed")
                ),

                indication=m.get(
                    "indication"
                ),

                notes=m.get(
                    "notes"
                ),

                extraction_confidence=m.get(
                    "confidence"
                ),

                match_confidence=(
                    m.get("match_confidence")
                    or top.get("score")
                ),

                # AI extraction can never approve a medicine.
                # The doctor must confirm it again.
                doctor_confirmed=False,
            )
        )

    # ---------------------------------------------------------
    # 7. SAVE VERSIONED CLINICAL NOTE
    # ---------------------------------------------------------
    if outcome.get("clinical_note"):
        clinical_count = (
            await db.execute(
                select(
                    func.count(
                        SummaryVersion.id
                    )
                ).where(
                    SummaryVersion.consultation_id
                    == c.id,
                    SummaryVersion.kind
                    == "clinical_note",
                )
            )
        ).scalar_one()

        db.add(
            SummaryVersion(
                consultation_id=c.id,
                kind="clinical_note",
                version=int(
                    clinical_count
                ) + 1,
                content=outcome[
                    "clinical_note"
                ],
                source="ai",
                model_name=settings.OLLAMA_MODEL,
            )
        )

    # ---------------------------------------------------------
    # 8. SAVE VERSIONED PATIENT SUMMARY
    # ---------------------------------------------------------
    if outcome.get("patient_summary_en"):
        patient_count = (
            await db.execute(
                select(
                    func.count(
                        SummaryVersion.id
                    )
                ).where(
                    SummaryVersion.consultation_id
                    == c.id,
                    SummaryVersion.kind
                    == "patient_summary",
                )
            )
        ).scalar_one()

        db.add(
            SummaryVersion(
                consultation_id=c.id,
                kind="patient_summary",
                version=int(
                    patient_count
                ) + 1,
                content=outcome[
                    "patient_summary_en"
                ],
                source="ai",
                model_name=settings.OLLAMA_MODEL,
            )
        )

async def _run_pipeline(consultation_id:int):
    async with AsyncSessionLocal() as db:
        try:
            c=await _load(db,consultation_id)
            c.status=ConsultationStatus.TRANSCRIBING
            c.pipeline_error=None
            await db.commit()
            audio=resolve_storage_ref(c.audio_path)
            if not audio or not audio.exists():
                raise FileNotFoundError("Consultation audio file is missing")

            outcome=await process_consultation(
                audio,patient_language=c.patient_language,
                primary_language=c.stt_primary_language,
                secondary_language=c.stt_secondary_language,
            )
            if not outcome.get("transcript_raw"):
                raise RuntimeError("Transcription did not produce text")

            c.raw_transcript=outcome["transcript_raw"]
            # Kept for backwards compatibility; no LLM mutation is applied.
            c.transcript_normalised=outcome["transcript_raw"]
            c.verified_transcript=None
            c.languages_detected=outcome.get("languages_detected") or []
            c.code_switched=bool(outcome.get("code_switched"))
            c.clinical_note=outcome.get("clinical_note")
            c.patient_summary_en=outcome.get("patient_summary_en")
            c.patient_summary_translated=outcome.get("patient_summary_translated")
            c.structured_data=outcome.get("structured_data") or {}
            c.translation_quality=outcome.get("translation_quality")
            c.translation_verified=bool(
                (outcome.get("translation_metadata") or {}).get("numeric_preserved",False)
                and (outcome.get("translation_metadata") or {}).get("script_valid",False)
            )
            c.dose_sentences_for_review=outcome.get("dose_sentences_for_review") or []
            c.audio_summary_path=to_storage_ref(outcome.get("audio_summary_path"))
            c.tts_backend=outcome.get("tts_backend")
            c.model_metadata=outcome.get("model_metadata") or {}
            c.pipeline_error=json.dumps(outcome.get("errors") or [],ensure_ascii=False) if outcome.get("errors") else None

            await _save_pipeline_rows(db,c,outcome)
            # Draft remains doctor-reviewable even if warning layers found issues.
            c.status=ConsultationStatus.SAFETY_REVIEW_REQUIRED if any(
                x.get("status") in {"warning","fail"} and not x.get("resolved",False)
                for x in (outcome.get("safety_checks") or [])
            ) else ConsultationStatus.DRAFTED
            await audit(db,c.doctor_id,"consultation.pipeline_complete","consultation",c.id,{
                "warnings":sum(1 for x in outcome.get("safety_checks",[]) if x.get("status")=="warning"),
                "errors":outcome.get("errors") or [],
            })
            await db.commit()
        except Exception as exc:
            logger.exception("Pipeline failed for consultation %s",consultation_id)
            try:
                c=await _load(db,consultation_id)
                c.status=ConsultationStatus.PROCESSING_FAILED
                c.pipeline_error=str(exc)
                await audit(db,c.doctor_id,"consultation.pipeline_failed","consultation",c.id,{"error":str(exc)})
                await db.commit()
            except Exception:
                await db.rollback()

@router.post("/",response_model=ConsultationPublic,status_code=201)
async def create_consultation(
    body:ConsultationCreate,
    db:AsyncSession=Depends(get_db),
    doctor:User=Depends(get_current_user),
):
    if doctor.role not in {UserRole.DOCTOR,UserRole.ADMIN}:
        raise HTTPException(status.HTTP_403_FORBIDDEN,"Doctor access required")
    if not body.doctor_consent or not body.patient_consent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,"Both doctor and patient consent are required")
    patient=(await db.execute(select(User).where(
        User.id==body.patient_id,User.role==UserRole.PATIENT,User.is_active.is_(True)
    ))).scalar_one_or_none()
    if not patient: raise HTTPException(status.HTTP_400_BAD_REQUEST,"Patient not found")

       # -----------------------------------------------------
    # DURABLE CONSULTATION ID
    # -----------------------------------------------------
    # Audit records intentionally survive consultation erasure.
    # Therefore a new consultation must never reuse an ID that
    # already exists in historical consultation audit records.
    #
    # sqlite_autoincrement protects fresh databases; this explicit
    # allocator also protects an existing database created before
    # AUTOINCREMENT was enabled.

    max_live_id = (
        await db.execute(
            select(
                func.max(
                    Consultation.id
                )
            )
        )
    ).scalar_one_or_none() or 0

    max_audited_id = (
        await db.execute(
            select(
                func.max(
                    AuditLog.target_id
                )
            ).where(
                AuditLog.target_type
                == "consultation"
            )
        )
    ).scalar_one_or_none() or 0

    next_consultation_id = (
        max(
            int(max_live_id),
            int(max_audited_id),
        )
        + 1
    )

    c=Consultation(
        id=next_consultation_id,
        doctor_id=doctor.id,
        patient_id=patient.id,
        doctor_consent=True,patient_consent=True,
        patient_language=body.patient_language,
        stt_primary_language=body.stt_primary_language,
        stt_secondary_language=body.stt_secondary_language,
        status=ConsultationStatus.RECORDING,
    )
    db.add(c);await db.flush()
    db.add(ConsentRecord(
        consultation_id=c.id,doctor_id=doctor.id,patient_id=patient.id,
        doctor_consent=True,patient_consent=True,method=body.consent_method,
        consent_version="final-1.0",
    ))
    await audit(db,doctor.id,"consent.granted","consultation",c.id,{
        "method":body.consent_method,"doctor_consent":True,"patient_consent":True
    })
    await audit(db,doctor.id,"consultation.created","consultation",c.id)
    return c

@router.post("/{cid}/audio",response_model=ConsultationPublic)
async def upload_audio(
    cid:int,file:UploadFile=File(...),
    db:AsyncSession=Depends(get_db),
    doctor:User=Depends(get_current_user),
):
    c=await _load(db,cid);require_owner_doctor(doctor,c)
    if c.status not in {ConsultationStatus.RECORDING, ConsultationStatus.PROCESSING_FAILED}:
        raise HTTPException(status.HTTP_409_CONFLICT,"Audio can only be uploaded before processing or when retrying a failed pipeline")
    allowed={".webm",".wav",".mp3",".m4a",".mp4",".ogg"}
    suffix=Path(file.filename or "recording.webm").suffix.lower() or ".webm"
    if suffix not in allowed: raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,"Unsupported audio type")
    dest=settings.UPLOAD_DIR/f"consultation_{c.id}{suffix}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file,fh)
    if dest.stat().st_size==0: raise HTTPException(status.HTTP_400_BAD_REQUEST,"Empty recording")
    c.audio_path=to_storage_ref(dest)
    c.status=ConsultationStatus.TRANSCRIBING
    await audit(db,doctor.id,"consultation.audio_uploaded","consultation",c.id,{"bytes":dest.stat().st_size})
    await db.flush()
    asyncio.create_task(_run_pipeline(c.id))
    return c

@router.get("/",response_model=list[ConsultationPublic])
async def list_consultations(
    status_filter:str|None=Query(None,alias="status"),
    db:AsyncSession=Depends(get_db),
    user:User=Depends(get_current_user),
):
    q=select(Consultation)
    if user.role==UserRole.PATIENT:
        q=q.where(
            Consultation.patient_id == user.id,
            Consultation.status.in_([
                ConsultationStatus.RELEASED,
                ConsultationStatus.CROSS_CHECKED,
            ]),
        )
    elif user.role==UserRole.DOCTOR:
        # Treating cases plus explicit review assignments only.
        assigned=select(CrossCheck.consultation_id).where(CrossCheck.reviewer_id==user.id)
        q=q.where((Consultation.doctor_id==user.id)|Consultation.id.in_(assigned))
    elif user.role==UserRole.CROSS_CHECK_DOCTOR:
        assigned=select(CrossCheck.consultation_id).where(CrossCheck.reviewer_id==user.id)
        q=q.where(Consultation.id.in_(assigned))
    elif user.role==UserRole.ASSISTANT:
        # Assistants never browse the consultation directory. Their only
        # clinical access is through /api/assistant-reviews/* assignment-scoped endpoints.
        q=q.where(Consultation.id == -1)
    if status_filter:
        try:q=q.where(Consultation.status==ConsultationStatus(status_filter.lower()))
        except Exception:pass
    res=await db.execute(q.order_by(Consultation.created_at.desc()))
    return [_api_view(user,x) for x in res.scalars()]

@router.get("/{cid}",response_model=ConsultationPublic)
async def get_consultation(
    cid:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)
):
    c=await _load(db,cid)
    await require_can_view_consultation(db,user,c)
    await audit(db,user.id,"consultation.viewed","consultation",c.id)
    return _api_view(user,c)

@router.get("/{cid}/transcript-segments",response_model=list[TranscriptSegmentPublic])
async def transcript_segments(
    cid:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)
):
    c=await _load(db,cid);await require_can_view_consultation(db,user,c)
    rows=(await db.execute(
        select(TranscriptSegment).where(TranscriptSegment.consultation_id==cid)
        .order_by(TranscriptSegment.segment_index)
    )).scalars()
    return list(rows)

@router.patch("/{cid}/transcript-segments/{segment_id}",response_model=TranscriptSegmentPublic)
async def update_transcript_segment(
    cid:int,segment_id:int,body:TranscriptSegmentUpdate,
    db:AsyncSession=Depends(get_db),doctor:User=Depends(get_current_user)
):
    c=await _load(db,cid);require_owner_doctor(doctor,c);_require_clinical_editable(c)
    seg=(await db.execute(select(TranscriptSegment).where(
        TranscriptSegment.id==segment_id,TranscriptSegment.consultation_id==cid
    ))).scalar_one_or_none()
    if not seg:raise HTTPException(status.HTTP_404_NOT_FOUND,"Segment not found")
    # ---------------------------------------------------------
    # EXPLICIT CLINICIAN TRANSCRIPT REVIEW
    # ---------------------------------------------------------
    #
    # A low-confidence segment may only leave needs_review when
    # reviewed text has actually been submitted by the doctor.
    #
    # The reviewed text may equal the raw text. That represents
    # an explicit "I listened and confirm this is accurate"
    # decision rather than silently accepting the ASR output.
    # ---------------------------------------------------------

    if body.text_reviewed is not None:
        reviewed_text = body.text_reviewed.strip()

        if not reviewed_text:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Reviewed transcript text cannot be empty.",
            )

        seg.text_reviewed = reviewed_text

    if body.speaker_label is not None:
        seg.speaker_label = body.speaker_label.strip()

    if (
        body.needs_review is False
        and seg.needs_review
        and not seg.text_reviewed
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                "Low-confidence speech cannot be marked reviewed "
                "without submitting clinician-reviewed transcript text."
            ),
        )

    if body.needs_review is not None:
        seg.needs_review = body.needs_review

    if seg.text_reviewed:
        seg.needs_review = False

    reviewed_as_accurate = bool(
        seg.text_reviewed
        and seg.text_reviewed.strip()
        == (seg.text_raw or "").strip()
    )

    await audit(
        db,
        doctor.id,
        "transcript.segment_reviewed",
        "consultation",
        cid,
        {
            "segment_id": segment_id,
            "reviewed_as_accurate": reviewed_as_accurate,
            "text_corrected": bool(
                seg.text_reviewed
                and seg.text_reviewed.strip()
                != (seg.text_raw or "").strip()
            ),
        },
    )
    
    # Rebuild verified transcript from reviewed/raw segments.
    rows = list(
        (
            await db.execute(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.consultation_id == cid
                )
                .order_by(
                    TranscriptSegment.segment_index
                )
            )
        ).scalars()
    )

    c.verified_transcript = " ".join(
        (x.text_reviewed or x.text_raw).strip()
        for x in rows
        if (x.text_reviewed or x.text_raw).strip()
    )

    meta = dict(c.model_metadata or {})

    meta["reviewed_transcript_stale"] = True
    meta["reviewed_transcript_updated_at"] = (
        datetime.utcnow().isoformat()
    )

    c.model_metadata = meta

    # A previous doctor-edited summary was based on
    # the previous transcript.
    c.doctor_edited_summary = None

    return seg
@router.post(
    "/{cid}/regenerate-reviewed",
    response_model=ConsultationPublic,
)
async def regenerate_from_reviewed_transcript(
    cid: int,
    db: AsyncSession = Depends(get_db),
    doctor: User = Depends(get_current_user),
):
    c = await _load(db, cid)

    require_owner_doctor(doctor, c)
    _require_clinical_editable(c)

    source = (
        c.verified_transcript or ""
    ).strip()

    if not source:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No doctor-reviewed transcript is available.",
        )

    rows = list(
        (
            await db.execute(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.consultation_id
                    == cid
                )
                .order_by(
                    TranscriptSegment.segment_index
                )
            )
        ).scalars()
    )

    reviewed_segments = []

    for row in rows:
        reviewed_segments.append(
            {
                "start": float(
                    row.start_seconds or 0
                ),
                "end": float(
                    row.end_seconds or 0
                ),
                "text": (
                    row.text_reviewed
                    or row.text_raw
                    or ""
                ).strip(),
                "language": row.language,
                "language_confidence":
                    row.language_confidence,
                "avg_logprob":
                    row.avg_logprob,
                "no_speech_prob":
                    row.no_speech_prob,
                "confidence":
                    row.confidence,
                "speaker":
                    row.speaker_label,
                "diarization_confidence":
                    row.diarization_confidence,
                "needs_review":
                    bool(row.needs_review),
            }
        )

    outcome = await process_consultation(
        None,
        patient_language=c.patient_language,
        primary_language=c.stt_primary_language,
        secondary_language=c.stt_secondary_language,
        transcript_override=source,
        transcript_segments_override=
            reviewed_segments,
    )

    if not outcome.get(
        "structured_data"
    ):
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            (
                "Regeneration failed during "
                "structured extraction."
            ),
        )

    if not outcome.get(
        "patient_summary_en"
    ):
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            (
                "Regeneration did not produce "
                "a patient summary."
            ),
        )

    # Preserve raw STT and verified transcript.
    # Replace only downstream AI-derived outputs.
    c.clinical_note = outcome.get(
        "clinical_note"
    )

    c.patient_summary_en = outcome.get(
        "patient_summary_en"
    )

    c.patient_summary_translated = (
        outcome.get(
            "patient_summary_translated"
        )
    )

    c.structured_data = (
        outcome.get("structured_data")
        or {}
    )

    c.translation_quality = outcome.get(
        "translation_quality"
    )

    translation_meta = (
        outcome.get(
            "translation_metadata"
        )
        or {}
    )

    c.translation_verified = bool(
        translation_meta.get(
            "numeric_preserved",
            False,
        )
        and translation_meta.get(
            "script_valid",
            False,
        )
    )

    c.dose_sentences_for_review = (
        outcome.get(
            "dose_sentences_for_review"
        )
        or []
    )

    old_audio = c.audio_summary_path

    new_audio = to_storage_ref(
        outcome.get(
            "audio_summary_path"
        )
    )

    c.audio_summary_path = new_audio

    if (
        old_audio
        and old_audio != new_audio
    ):
        safe_unlink(old_audio)

    c.tts_backend = outcome.get(
        "tts_backend"
    )

    metadata = dict(
        outcome.get(
            "model_metadata"
        )
        or {}
    )

    metadata[
        "reviewed_transcript_stale"
    ] = False

    metadata[
        "regenerated_from_reviewed_transcript"
    ] = True

    metadata[
        "regenerated_at"
    ] = datetime.utcnow().isoformat()

    c.model_metadata = metadata

    c.pipeline_error = (
        json.dumps(
            outcome.get("errors") or [],
            ensure_ascii=False,
        )
        if outcome.get("errors")
        else None
    )

    # The previous doctor summary/approval can no
    # longer be reused after clinical source changes.
    c.doctor_edited_summary = None
    c.approved_at = None

    await _save_pipeline_rows(
        db,
        c,
        outcome,
        replace_transcript_segments=False,
    )

    c.status = (
        ConsultationStatus.SAFETY_REVIEW_REQUIRED
        if any(
            check.get("status")
            in {"warning", "fail"}
            and not check.get(
                "resolved",
                False,
            )
            for check in (
                outcome.get(
                    "safety_checks"
                )
                or []
            )
        )
        else ConsultationStatus.DRAFTED
    )

    await audit(
        db,
        doctor.id,
        "consultation.regenerated_from_reviewed_transcript",
        "consultation",
        cid,
        {
            "source":
                "verified_transcript",
        },
    )

    return c
@router.get("/{cid}/safety",response_model=list[SafetyCheckPublic])
async def safety_checks(
    cid:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)
):
    c=await _load(db,cid);await require_can_view_consultation(db,user,c)
    return list((await db.execute(
        select(SafetyCheck).where(SafetyCheck.consultation_id==cid).order_by(SafetyCheck.created_at)
    )).scalars())

@router.post("/{cid}/safety/{check_id}/resolve",response_model=SafetyCheckPublic)
async def resolve_safety(
    cid: int,
    check_id: int,
    confirm_translation: bool = False,
    confirm_grounding: bool = False,
    db: AsyncSession = Depends(get_db),
    doctor: User = Depends(get_current_user),
):
    c = await _load(db, cid)
    require_owner_doctor(doctor, c)

    if c.released_at:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Released consultations are immutable",
        )

    chk = (
        await db.execute(
            select(SafetyCheck).where(
                SafetyCheck.id == check_id,
                SafetyCheck.consultation_id == cid,
            )
        )
    ).scalar_one_or_none()

    if not chk:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Safety check not found",
        )

    if chk.resolved:
        return chk


    # =========================================================
    # STT CONFIDENCE
    # =========================================================
    #
    # The Safety panel itself cannot dismiss uncertain speech.
    # Every highlighted segment must first be explicitly reviewed
    # in the transcript-review interface.
    # =========================================================

    if chk.check_type == "stt_confidence":

        pending_segment = (
            await db.execute(
                select(TranscriptSegment.id)
                .where(
                    TranscriptSegment.consultation_id == cid,
                    TranscriptSegment.needs_review.is_(True),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

        if pending_segment is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                (
                    "Speech-confidence warnings cannot be resolved "
                    "while transcript segments still require review. "
                    "Review or correct every highlighted segment first."
                ),
            )


    # =========================================================
    # NLI GROUNDING
    # =========================================================

    if (
        chk.check_type == "nli_grounding"
        and chk.status in {"warning", "fail"}
        and not confirm_grounding
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                "Summary-grounding warnings require explicit "
                "clinician confirmation. Verify that the patient-facing "
                "claim is supported by the reviewed consultation before "
                "confirming it."
            ),
        )


    # =========================================================
    # TRANSLATION INTEGRITY
    # =========================================================

    if (
        chk.check_type == "translation_integrity"
        and not confirm_translation
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                "Translation integrity warnings require explicit "
                "clinician verification. Review the translated patient "
                "summary, medicine names, dose, frequency, duration, "
                "numbers, negation and clinical meaning before confirming."
            ),
        )


    now = datetime.utcnow()

    chk.resolved = True
    chk.resolved_by_id = doctor.id
    chk.resolved_at = now

    audit_details = {
        "check_id": check_id,
        "type": chk.check_type,
    }


    if chk.check_type == "stt_confidence":

        audit_details[
            "all_flagged_segments_reviewed"
        ] = True

        await audit(
            db,
            doctor.id,
            "stt.clinician_review_completed",
            "consultation",
            cid,
            {
                "check_id": check_id,
            },
        )


    if (
        chk.check_type == "nli_grounding"
        and chk.status in {"warning", "fail"}
    ):

        audit_details[
            "manual_grounding_verification"
        ] = True

        await audit(
            db,
            doctor.id,
            "nli.clinician_verified",
            "consultation",
            cid,
            {
                "check_id": check_id,
                "statement": chk.statement,
            },
        )


    if chk.check_type == "translation_integrity":

        audit_details.update(
            {
                "manual_translation_verification": True,
                "automated_translation_verified":
                    bool(c.translation_verified),
                "patient_language":
                    c.patient_language,
            }
        )

        await audit(
            db,
            doctor.id,
            "translation.clinician_verified",
            "consultation",
            cid,
            {
                "check_id": check_id,
                "language": c.patient_language,
                "automated_verification":
                    bool(c.translation_verified),
            },
        )


    await audit(
        db,
        doctor.id,
        "safety.resolved",
        "consultation",
        cid,
        audit_details,
    )

    return chk


@router.post("/{cid}/medications/{idx}",response_model=ConsultationPublic)
async def update_medication(
    cid:int,idx:int,body:MedicationUpdate,
    db:AsyncSession=Depends(get_db),doctor:User=Depends(get_current_user)
):
    c=await _load(db,cid);require_owner_doctor(doctor,c);_require_clinical_editable(c)
    meds=_legacy_med_list(c)
    if idx<0 or idx>=len(meds):raise HTTPException(status.HTTP_404_NOT_FOUND,"Medication not found")
    med = dict(
        meds[idx]
    )

    original_name = (
        med.get("name")
        or ""
    ).strip()

    fields = (
        "name",
        "dose",
        "strength",
        "dose_unit",
        "dosage_form",
        "route",
        "frequency",
        "timing",
        "food_instruction",
        "duration",
        "as_needed",
        "indication",
        "notes",
    )

    for key in fields:
        val = getattr(
            body,
            key,
            None,
        )

        if val is not None:
            med[key] = val


    # -----------------------------------------------------
    # MANUAL NAME EDIT != CANONICAL TERMINOLOGY IDENTITY
    # -----------------------------------------------------

    new_name = (
        med.get("name")
        or ""
    ).strip()

    manually_changed_name = (
        body.name is not None
        and new_name.casefold()
        != original_name.casefold()
    )

    if (
        manually_changed_name
        and body.concept_id is None
    ):
        # The doctor may enter a local brand or manually correct
        # spelling, but that text must not silently become an
        # RxNorm/terminology canonical identity.
        med["concept_id"] = None
        med["canonical_name"] = None
        med["generic_name"] = None
        med["brand_name"] = None
        med["match_confidence"] = None


    # -----------------------------------------------------
    # VERIFIED TERMINOLOGY SELECTION
    # -----------------------------------------------------

    if body.concept_id is not None:

        concept = (
            await db.execute(
                select(
                    MedicationConcept
                ).where(
                    MedicationConcept.id
                    == body.concept_id
                )
            )
        ).scalar_one_or_none()

        if not concept:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Selected medication terminology concept was not found",
            )

        med["name"] = (
            concept.display_name
        )

        med["canonical_name"] = (
            concept.display_name
        )

        med["generic_name"] = (
            concept.generic_name
        )

        med["brand_name"] = (
            concept.brand_name
        )

        med["match_confidence"] = 1.0

        med["concept_id"] = (
            concept.id
        )


    if body.confirm_identity:
        med[
            "doctor_confirmed"
        ] = True
    meds[idx]=med;_set_legacy_meds(c,meds)

    row=(await db.execute(select(ConsultationMedication).where(
        ConsultationMedication.consultation_id==cid,ConsultationMedication.source_index==idx
    ).order_by(ConsultationMedication.id))).scalars().first()
    if not row:
        row=ConsultationMedication(consultation_id=cid,source="doctor",source_index=idx)
        db.add(row)
        row.raw_name = (
        med.get("name_as_heard")
        or med.get("name")
    )

    row.canonical_name = (
        med.get(
            "canonical_name"
        )
    )

    row.generic_name = (
        med.get(
            "generic_name"
        )
    )

    row.brand_name = (
        med.get(
            "brand_name"
        )
    )

    row.concept_id = (
        med.get(
            "concept_id"
        )
    )
    for key in ("strength","dose","dose_unit","dosage_form","route","frequency","timing",
                "food_instruction","duration","as_needed","indication","notes"):
        if key in med:setattr(row,key,med.get(key))
    if body.confirm_identity or body.confirm_instructions:
        row.doctor_confirmed=True
        med["doctor_confirmed"]=True
        meds[idx]=med;_set_legacy_meds(c,meds)
    await audit(db,doctor.id,"consultation.medication_corrected","consultation",cid,{
        "index":idx,"identity_confirmed":body.confirm_identity,
        "instructions_confirmed":body.confirm_instructions,
    })
    return c

@router.delete("/{cid}/medications/{idx}",response_model=ConsultationPublic)
async def remove_medication(
    cid:int,idx:int,db:AsyncSession=Depends(get_db),doctor:User=Depends(get_current_user)
):
    c=await _load(db,cid);require_owner_doctor(doctor,c);_require_clinical_editable(c)
    meds=_legacy_med_list(c)
    if idx<0 or idx>=len(meds):raise HTTPException(status.HTTP_404_NOT_FOUND,"Medication not found")
    meds.pop(idx);_set_legacy_meds(c,meds)
    await db.execute(delete(ConsultationMedication).where(
        ConsultationMedication.consultation_id==cid,ConsultationMedication.source_index==idx
    ))
    # Reindex later rows.
    rows=list((await db.execute(select(ConsultationMedication).where(
        ConsultationMedication.consultation_id==cid
    ).order_by(ConsultationMedication.source_index))).scalars())
    for i,row in enumerate(rows):row.source_index=i
    await audit(db,doctor.id,"consultation.medication_removed","consultation",cid,{"index":idx})
    return c

@router.post("/{cid}/medications",response_model=ConsultationPublic)
async def add_medication(
    cid:int,body:MedicationUpdate,
    db:AsyncSession=Depends(get_db),doctor:User=Depends(get_current_user)
):
    c=await _load(db,cid);require_owner_doctor(doctor,c);_require_clinical_editable(c)
    meds=_legacy_med_list(c)
    med={
        "name":body.name or "","name_as_heard":"","confidence":1.0,
        "dose":body.dose,"strength":body.strength,"dose_unit":body.dose_unit,
        "dosage_form":body.dosage_form,"route":body.route,"frequency":body.frequency,
        "timing":body.timing,"food_instruction":body.food_instruction,
        "duration":body.duration,"as_needed":bool(body.as_needed),
        "indication":body.indication,"notes":body.notes,
        "doctor_confirmed":bool(body.confirm_identity and body.confirm_instructions),
        "suggestions":[],
    }
    meds.append(med);_set_legacy_meds(c,meds)
    db.add(ConsultationMedication(
        consultation_id=cid,source="doctor",source_index=len(meds)-1,
        raw_name=body.name,canonical_name=body.name,strength=body.strength,
        dose=body.dose,dose_unit=body.dose_unit,dosage_form=body.dosage_form,
        route=body.route,frequency=body.frequency,timing=body.timing,
        food_instruction=body.food_instruction,duration=body.duration,
        as_needed=bool(body.as_needed),indication=body.indication,notes=body.notes,
        doctor_confirmed=med["doctor_confirmed"],
    ))
    await audit(db,doctor.id,"consultation.medication_added","consultation",cid)
    return c


async def _merge_prescription_candidates(
    db: AsyncSession, c: Consultation, structured: dict, actor_id: int
) -> None:
    """Merge OCR medication candidates without silently accepting them.

    Existing transcript medication rows are reconciled by terminology concept/name.
    Conflicting strength/dose instructions create explicit safety warnings.
    """
    meds=_legacy_med_list(c)
    for pmed in (structured or {}).get("medications",[]) or []:
        raw=(pmed.get("name_as_heard") or pmed.get("name") or "").strip()
        sugg=medication_index.suggest(raw,5) if raw else []
        top=sugg[0] if sugg else {}
        pmed=dict(pmed)
        pmed["suggestions"]=sugg
        pmed["match_confidence"]=top.get("score",0.0)
        pmed["concept_id"]=top.get("concept_id")
        pmed["source"]="prescription"
        pmed["doctor_confirmed"]=False

        def same(existing):
            if top.get("concept_id") and existing.get("concept_id")==top.get("concept_id"):
                return True
            a=(existing.get("name") or "").lower().strip()
            b=(top.get("display_name") or pmed.get("name") or "").lower().strip()
            return bool(a and b and (a==b or a in b or b in a))

        match_idx=next((i for i,m in enumerate(meds) if same(m)),None)
        if match_idx is not None:
            existing=meds[match_idx]
            conflicts={}
            for field in ("strength","dose","frequency","duration"):
                a=(existing.get(field) or "").strip().lower()
                b=(pmed.get(field) or "").strip().lower()
                if a and b and a not in {"not specified","unknown"} and b not in {"not specified","unknown"} and a!=b:
                    conflicts[field]={"transcript":a,"prescription":b}
            if conflicts:
                existing["discrepancy_status"]="review_required"
                existing["prescription_candidate"]=pmed
                meds[match_idx]=existing
                db.add(SafetyCheck(
                    consultation_id=c.id,check_type="medication_discrepancy",
                    status="warning",severity="high",
                    statement=existing.get("name") or raw,
                    evidence="Transcript and prescription instructions differ",
                    details=conflicts,resolved=False,
                ))
            else:
                existing["prescription_match"]="consistent"
                existing["prescription_candidate"]=pmed
                meds[match_idx]=existing
            continue

        idx=len(meds)
        meds.append(pmed)
        db.add(ConsultationMedication(
            consultation_id=c.id,source="prescription",source_index=idx,
            raw_name=raw,concept_id=top.get("concept_id"),
            canonical_name=top.get("display_name") or pmed.get("name"),
            generic_name=top.get("generic_name"),brand_name=top.get("brand_name"),
            strength=pmed.get("strength") or top.get("strength"),
            dose=pmed.get("dose"),dose_unit=pmed.get("dose_unit"),
            dosage_form=pmed.get("dosage_form") or top.get("dosage_form"),
            route=pmed.get("route") or top.get("route"),
            frequency=pmed.get("frequency"),timing=pmed.get("timing"),
            food_instruction=pmed.get("food_instruction"),duration=pmed.get("duration"),
            as_needed=bool(pmed.get("as_needed")),indication=pmed.get("indication"),
            notes=pmed.get("notes"),extraction_confidence=pmed.get("confidence"),
            match_confidence=top.get("score"),doctor_confirmed=False,
        ))
        db.add(SafetyCheck(
            consultation_id=c.id,check_type="prescription_medication_review",
            status="warning",severity="high",statement=raw,
            evidence=top.get("display_name") if top else "No terminology match",
            score=top.get("score"),details={"source":"prescription"},resolved=False,
        ))
    _set_legacy_meds(c,meds)
    await audit(db,actor_id,"prescription.medications_reconciled","consultation",c.id,
                {"candidates":len((structured or {}).get("medications",[]) or [])})


def _approval_source_hash(
    text: str,
) -> str:
    return hashlib.sha256(
        (text or "").encode("utf-8")
    ).hexdigest()


async def _final_delivery_is_current(
    db: AsyncSession,
    c: Consultation,
    source_summary: str,
) -> bool:
    """
    True only when the current patient delivery was
    generated from this exact doctor-reviewed summary.

    This prevents the second Approve click from
    regenerating the same translation warning after
    the clinician has already reviewed/resolved it.
    """

    if c.patient_language == "en":
        return (
            (c.patient_summary_translated or "")
            == source_summary
        )

    expected_hash = _approval_source_hash(
        source_summary
    )

    record_id = (
        await db.execute(
            select(
                TranslationRecord.id
            )
            .where(
                TranslationRecord.consultation_id
                == c.id,

                TranslationRecord.language
                == c.patient_language,

                TranslationRecord.source_hash
                == expected_hash,
            )
            .order_by(
                TranslationRecord.id.desc()
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    return (
        record_id is not None
        and bool(
            c.patient_summary_translated
        )
    )


async def _generate_delivery(
    db: AsyncSession,
    c: Consultation,
    source_summary: str,
    actor_id: int,
):
    # Patient delivery is part of the doctor-approved package.
    # Never create a new translation/TTS result or warning
    # after approval.
    if (
        c.approved_at is not None
        or c.status in {
            ConsultationStatus.APPROVED,
            ConsultationStatus.RELEASED,
            ConsultationStatus.UNDER_CROSS_CHECK,
            ConsultationStatus.CROSS_CHECKED,
        }
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                "Patient delivery is locked after doctor approval. "
                "Create/review the final delivery before approval."
            ),
        )

    target = c.patient_language

    # ---------------------------------------------------------
    # 1. TRANSLATE APPROVED ENGLISH SUMMARY
    # ---------------------------------------------------------
    if target != "en":
        tx = await asyncio.to_thread(
            translation.translate_with_metadata,
            source_summary,
            "en",
            target,
            c.structured_data or {},
        )
    else:
        tx = {
            "translated": source_summary,
            "quality": "verified",
            "dose_sentences": [],
            "source_hash": "",
            "back_translation": source_summary,
            "numeric_preserved": True,
            "medication_preserved": True,
            "script_valid": True,
            "semantic_status": "source_language",
            "semantic_score": 1.0,
        }

    # ---------------------------------------------------------
    # 2. SAVE TRANSLATED PATIENT SUMMARY
    # ---------------------------------------------------------
    c.patient_summary_translated = (
        tx.get("translated") or ""
    )

    c.translation_quality = tx.get(
        "quality"
    )

    c.translation_verified = bool(
        tx.get("numeric_preserved")
        and tx.get("medication_preserved")
        and tx.get("script_valid")
        and tx.get("semantic_status")
        in {
            "pass",
            "source_language",
        }
    )

    c.dose_sentences_for_review = (
        tx.get("dose_sentences")
        or []
    )

    # ---------------------------------------------------------
    # 3. SAVE TRANSLATION RECORD
    # ---------------------------------------------------------
    db.add(
        TranslationRecord(
            consultation_id=c.id,
            language=target,
            source_hash=(
                tx.get("source_hash")
                or ""
            ),
            translated_text=(
                tx.get("translated")
                or ""
            ),
            back_translation=tx.get(
                "back_translation"
            ),
            numeric_preserved=bool(
                tx.get(
                    "numeric_preserved"
                )
            ),
            medication_preserved=bool(
                tx.get(
                    "medication_preserved"
                )
            ),
            script_valid=bool(
                tx.get(
                    "script_valid"
                )
            ),
            semantic_status=(
                tx.get(
                    "semantic_status"
                )
                or "unavailable"
            ),
            semantic_score=tx.get(
                "semantic_score"
            ),
            model_name=settings.NLLB_MODEL,
        )
    )

    # ---------------------------------------------------------
    # 4. REMOVE OLD TRANSLATION WARNING
    # ---------------------------------------------------------
    await db.execute(
        delete(SafetyCheck).where(
            SafetyCheck.consultation_id
            == c.id,
            SafetyCheck.check_type
            == "translation_integrity",
            SafetyCheck.resolved.is_(
                False
            ),
        )
    )

    # ---------------------------------------------------------
    # 5. CREATE TRANSLATION SAFETY WARNING IF NEEDED
    # ---------------------------------------------------------
    if not c.translation_verified:
        db.add(
            SafetyCheck(
                consultation_id=c.id,
                check_type=
                    "translation_integrity",
                status="warning",
                severity="high",
                statement=(
                    f"Verify {target} translation "
                    "before approval."
                ),
                evidence=source_summary,
                score=tx.get(
                    "semantic_score"
                ),
                details={
                    "numeric_preserved":
                        bool(
                            tx.get(
                                "numeric_preserved"
                            )
                        ),
                    "medication_preserved":
                        bool(
                            tx.get(
                                "medication_preserved"
                            )
                        ),
                    "script_valid":
                        bool(
                            tx.get(
                                "script_valid"
                            )
                        ),
                    "semantic_status":
                        (
                            tx.get(
                                "semantic_status"
                            )
                            or "unavailable"
                        ),
                    "back_translation":
                        tx.get(
                            "back_translation"
                        ),
                    "script_error":
                        tx.get(
                            "script_error"
                        ),
                },
                resolved=False,
            )
        )

    # ---------------------------------------------------------
    # 6. SAFE TTS
    # ---------------------------------------------------------
    # Audio must NOT be generated when the output contains
    # an invalid script such as Hindi/Devanagari.
    audio = None

    if (
        tx.get("translated")
        and tx.get("script_valid")
    ):
        alternate = None

        # Punjabi Shahmukhi is displayed only in Shahmukhi.
        # Gurmukhi is allowed internally ONLY for the Punjabi
        # voice backend if required.
        if target == "pa_shah":
            alternate = await asyncio.to_thread(
                translation.translate_nllb,
                source_summary,
                "en",
                "pa",
            )

        audio = await asyncio.to_thread(
            tts.synthesise,
            tx["translated"],
            target,
            alternate,
        )

    # ---------------------------------------------------------
    # 7. SAVE AUDIO INFORMATION
    # ---------------------------------------------------------
    if audio:
        c.audio_summary_path = (
            to_storage_ref(audio)
        )

        c.tts_backend = (
            tts.backend_used(
                target
            )
        )

    else:
        c.audio_summary_path = None
        c.tts_backend = "none"

    # ---------------------------------------------------------
    # 8. REMOVE PREVIOUS TTS WARNING
    # ---------------------------------------------------------
    await db.execute(
        delete(SafetyCheck).where(
            SafetyCheck.consultation_id
            == c.id,
            SafetyCheck.check_type
            == "tts_generation",
            SafetyCheck.resolved.is_(
                False
            ),
        )
    )

    # ---------------------------------------------------------
    # 9. CREATE TTS WARNING IF AUDIO FAILED
    # ---------------------------------------------------------
    if not audio:
        if not tx.get(
            "script_valid"
        ):
            reason = (
                "Translation failed script "
                "validation, so audio was blocked."
            )
        else:
            reason = (
                "Audio synthesis did not "
                "produce an audio file."
            )

        db.add(
            SafetyCheck(
                consultation_id=c.id,
                check_type=
                    "tts_generation",
                status="warning",
                severity="medium",
                statement=(
                    f"Audio generation failed "
                    f"for {target}."
                ),
                evidence=None,
                details={
                    "language": target,
                    "reason": reason,
                    "script_valid":
                        bool(
                            tx.get(
                                "script_valid"
                            )
                        ),
                },
                resolved=False,
            )
        )

    # ---------------------------------------------------------
    # 10. AUDIT
    # ---------------------------------------------------------
    await audit(
        db,
        actor_id,
        "consultation.delivery_generated",
        "consultation",
        c.id,
        {
            "language":
                target,
            "translation_quality":
                c.translation_quality,
            "translation_verified":
                c.translation_verified,
            "tts":
                c.tts_backend,
        },
    )

@router.post("/{cid}/prescription",response_model=OCRResult)
async def upload_prescription(
    cid:int,file:UploadFile=File(...),
    db:AsyncSession=Depends(get_db),doctor:User=Depends(get_current_user)
):
    c=await _load(db,cid);require_owner_doctor(doctor,c);_require_clinical_editable(c)
    suffix=Path(file.filename or "rx.png").suffix.lower()
    if suffix not in {".png",".jpg",".jpeg",".heic",".heif",".webp",".tif",".tiff"}:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,"Unsupported prescription image type")
    dest=settings.UPLOAD_DIR/f"prescription_{c.id}{suffix}"
    with dest.open("wb") as fh:shutil.copyfileobj(file.file,fh)
    if dest.stat().st_size>settings.OCR_MAX_UPLOAD_MB*1024*1024:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,"Prescription image is too large")
    result=await ocr_svc.extract_prescription_structure(dest)
    o=result["ocr"];structured=result.get("structured") or {}
    c.prescription_image_path=to_storage_ref(dest)
    c.prescription_ocr_text=o.get("text") or ""
    c.prescription_ocr_confidence=o.get("confidence")
    existing=(await db.execute(select(Prescription).where(Prescription.consultation_id==cid))).scalar_one_or_none()
    if not existing:
        existing=Prescription(consultation_id=cid);db.add(existing)
    existing.image_path=to_storage_ref(dest);existing.raw_ocr_text=o.get("text") or ""
    existing.ocr_engine=o.get("engine");existing.ocr_confidence=o.get("confidence")
    existing.structured_data=structured
    await _merge_prescription_candidates(db,c,structured,doctor.id)
    await audit(db,doctor.id,"prescription.ocr","consultation",cid,{
        "engine":o.get("engine"),"confidence":o.get("confidence")
    })
    return OCRResult(
        text=o.get("text") or "",confidence=o.get("confidence") or 0.0,
        available=bool(o.get("available")),engine=o.get("engine"),
        warning=o.get("warning"),structured=structured,
    )

@router.patch("/{cid}/prescription/ocr",response_model=OCRResult)
async def correct_ocr(
    cid:int,body:OCRCorrection,
    db:AsyncSession=Depends(get_db),doctor:User=Depends(get_current_user)
):
    c=await _load(db,cid);require_owner_doctor(doctor,c);_require_clinical_editable(c)
    p=(await db.execute(select(Prescription).where(Prescription.consultation_id==cid))).scalar_one_or_none()
    if not p:raise HTTPException(status.HTTP_404_NOT_FOUND,"Prescription not found")
    p.corrected_ocr_text=body.text;c.prescription_ocr_text=body.text
    structured=await ocr_svc.structure_ocr_text(body.text)
    p.structured_data=structured
    # Replace previous unconfirmed prescription-only rows before re-reconciliation.
    await db.execute(delete(ConsultationMedication).where(
        ConsultationMedication.consultation_id==cid,
        ConsultationMedication.source=="prescription",
        ConsultationMedication.doctor_confirmed.is_(False),
    ))
    meds=[m for m in _legacy_med_list(c) if m.get("source")!="prescription"]
    _set_legacy_meds(c,meds)
    await _merge_prescription_candidates(db,c,structured,doctor.id)
    await audit(db,doctor.id,"prescription.ocr_corrected","consultation",cid)
    return OCRResult(text=body.text,confidence=p.ocr_confidence or 0.0,available=True,
                     engine=p.ocr_engine,structured=structured)

@router.post("/{cid}/approve",response_model=ConsultationPublic)
async def approve(
    cid:int,
    body:DoctorApproval,
    db:AsyncSession=Depends(get_db),
    doctor:User=Depends(get_current_user)
):
    c=await _load(db,cid)

    require_owner_doctor(
        doctor,
        c,
    )

    _require_clinical_editable(c)

    # ---------------------------------------------------------
    # 1. Reviewed transcript must be current
    # ---------------------------------------------------------

    if (
        c.model_metadata or {}
    ).get(
        "reviewed_transcript_stale"
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                "The transcript was changed by the "
                "doctor. Regenerate the AI outputs "
                "from the reviewed transcript before "
                "approval."
            ),
        )

    # ---------------------------------------------------------
    # 2. Assistant review must be completed
    # ---------------------------------------------------------

    pending_assistant = (
        await db.execute(
            select(
                AssistantReview.id
            ).where(
                AssistantReview.consultation_id
                == cid,

                AssistantReview.status
                == "pending",
            )
        )
    ).scalar_one_or_none()

    if pending_assistant is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                "This case is with the assigned "
                "assistant. Wait for 'I have checked' "
                "before final doctor approval."
            ),
        )

    if not c.patient_summary_en:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Summary not ready",
        )

    # ---------------------------------------------------------
    # 3. Medication confirmation + schedule validation
    #    ALL happen before approval
    # ---------------------------------------------------------

    rows = await _confirmed_medication_rows(
        db,
        cid,
    )

    if rows:

        unconfirmed = [
            med
            for med in rows
            if not med.doctor_confirmed
        ]

        if unconfirmed:

            names = ", ".join(
                (
                    med.canonical_name
                    or med.raw_name
                    or f"Medication #{med.id}"
                )
                for med in unconfirmed
            )

            raise HTTPException(
                status.HTTP_409_CONFLICT,
                (
                    "Confirm medication identity and "
                    "instructions before approval: "
                    f"{names}"
                ),
            )

        for med in rows:

            parsed = scheduler.parse_frequency(
                med.frequency
            )

            # PRN deliberately has no fixed timetable.
            if (
                med.as_needed
                or parsed.get("kind")
                == "prn"
            ):
                continue

            problem = (
                _validate_medication_schedule(
                    med
                )
            )

            if problem:

                name = (
                    med.canonical_name
                    or med.raw_name
                    or "Medication"
                )

                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    (
                        f"Cannot approve: {name} has "
                        "an invalid medication schedule — "
                        f"{problem}. Correct the "
                        "frequency/duration first."
                    ),
                )

    else:

        # Compatibility with older cases still storing
        # medication confirmation in structured_data.
        meds = _legacy_med_list(c)

        unconfirmed = [
            i
            for i,m in enumerate(meds)
            if not m.get(
                "doctor_confirmed"
            )
        ]

        if unconfirmed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                (
                    "Confirm medication identity/"
                    "instructions before approval "
                    f"(rows: {unconfirmed})"
                ),
            )

    # ---------------------------------------------------------
    # 4. Determine exact final doctor-reviewed summary
    # ---------------------------------------------------------

    source = (
        body.edited_summary.strip()
        if (
            body.edited_summary
            and body.edited_summary.strip()
        )
        else (
            c.doctor_edited_summary
            or c.patient_summary_en
        )
    )

    # Still a draft here.
    c.doctor_edited_summary = source

    # ---------------------------------------------------------
    # 5. Existing NON-delivery warnings must be resolved
    # ---------------------------------------------------------

    existing_unresolved = list(
        (
            await db.execute(
                select(
                    SafetyCheck
                ).where(
                    SafetyCheck.consultation_id
                    == cid,

                    SafetyCheck.resolved.is_(
                        False
                    ),

                    SafetyCheck.status.in_(
                        [
                            "warning",
                            "fail",
                        ]
                    ),

                    # Delivery checks will be refreshed
                    # from the final edited summary below.
                    SafetyCheck.check_type.notin_(
                        [
                            "translation_integrity",
                            "tts_generation",
                        ]
                    ),
                )
            )
        ).scalars()
    )

    if existing_unresolved:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                f"Resolve "
                f"{len(existing_unresolved)} "
                "safety warning(s) before "
                "approval."
            ),
        )

    # ---------------------------------------------------------
    # 6. Generate FINAL translation/TTS BEFORE APPROVAL
    # ---------------------------------------------------------

    delivery_current = (
        await _final_delivery_is_current(
            db,
            c,
            source,
        )
    )

    if not delivery_current:

        await _generate_delivery(
            db,
            c,
            source,
            doctor.id,
        )

        # Ensure newly-created SafetyCheck rows are visible
        # to the query immediately below.
        await db.flush()

    # ---------------------------------------------------------
    # 7. Re-check ALL warnings after final delivery generation
    # ---------------------------------------------------------

    unresolved = list(
        (
            await db.execute(
                select(
                    SafetyCheck
                ).where(
                    SafetyCheck.consultation_id
                    == cid,

                    SafetyCheck.resolved.is_(
                        False
                    ),

                    SafetyCheck.status.in_(
                        [
                            "warning",
                            "fail",
                        ]
                    ),
                )
            )
        ).scalars()
    )

    if unresolved:

        # Save the generated translation/TTS and warning
        # so the doctor can review it on screen.
        #
        # IMPORTANT: consultation remains UNAPPROVED.
        await audit(
            db,
            doctor.id,
            "consultation.approval_blocked",
            "consultation",
            cid,
            {
                "unresolved_warnings":
                    len(unresolved)
            },
        )

        await db.commit()

        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                "Final pre-approval checks found "
                f"{len(unresolved)} warning(s). "
                "Review and resolve them, then "
                "press Approve again. "
                "The case has NOT been approved."
            ),
        )

    # ---------------------------------------------------------
    # 8. ZERO warnings:
    #    NOW create approved summary version
    # ---------------------------------------------------------

    count = (
        await db.execute(
            select(
                func.count(
                    SummaryVersion.id
                )
            ).where(
                SummaryVersion.consultation_id
                == cid,

                SummaryVersion.kind
                == "patient_summary",
            )
        )
    ).scalar_one()

    db.add(
        SummaryVersion(
            consultation_id=cid,
            kind="patient_summary",
            version=int(count)+1,
            content=source,
            source="doctor",
            created_by_id=doctor.id,
            approved=True,
        )
    )

    # ---------------------------------------------------------
    # 9. ONLY NOW mark APPROVED
    # ---------------------------------------------------------

    c.status = (
        ConsultationStatus.APPROVED
    )

    c.approved_at = datetime.utcnow()

    await audit(
        db,
        doctor.id,
        "consultation.approved",
        "consultation",
        cid,
        {
            "edited":
                source
                != c.patient_summary_en,

            "warnings_remaining": 0,
        },
    )

    return c


@router.post(
    "/{cid}/release",
    response_model=ConsultationPublic,
)
async def release(
    cid: int,
    db: AsyncSession = Depends(get_db),
    doctor: User = Depends(get_current_user),
):
    c = await _load(db, cid)
    require_owner_doctor(doctor, c)

    pending_assistant = (await db.execute(select(AssistantReview.id).where(
        AssistantReview.consultation_id == cid,
        AssistantReview.status == "pending",
    ))).scalar_one_or_none()
    if pending_assistant is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Assistant pre-review is still pending; final doctor release is blocked until it is returned.",
        )

    if c.status != ConsultationStatus.APPROVED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Doctor approval is required before release",
        )

    unresolved = (
        await db.execute(
            select(func.count(SafetyCheck.id)).where(
                SafetyCheck.consultation_id == cid,
                SafetyCheck.resolved.is_(False),
                SafetyCheck.status.in_(
                    ["warning", "fail"]
                ),
            )
        )
    ).scalar_one()

    if unresolved:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                f"Resolve {int(unresolved)} safety "
                "warning(s), including translation "
                "checks, before release."
            ),
        )

    # ConsultationMedication is now the authoritative
    # medication source.
    rows = await _confirmed_medication_rows(
        db,
        cid,
    )

    if rows:
        unconfirmed = [
            row
            for row in rows
            if not row.doctor_confirmed
        ]

        if unconfirmed:
            names = ", ".join(
                row.canonical_name
                or row.raw_name
                or f"Medication #{row.id}"
                for row in unconfirmed
            )

            raise HTTPException(
                status.HTTP_409_CONFLICT,
                (
                    "All medications must be confirmed "
                    f"before release: {names}"
                ),
            )

    fixed_meds = []

    for med in rows:
        parsed = scheduler.parse_frequency(
            med.frequency
        )

        if (
            med.as_needed
            or parsed.get("kind") == "prn"
        ):
            continue

        problem = _validate_medication_schedule(
            med
        )

        if problem:
            name = (
                med.canonical_name
                or med.raw_name
                or "Medication"
            )

            raise HTTPException(
                status.HTTP_409_CONFLICT,
                (
                    f"Cannot release: {name} has an "
                    f"invalid medication schedule — "
                    f"{problem}. "
                    "Correct and confirm the medication "
                    "instructions first."
                ),
            )

        fixed_meds.append(med)

    # Remove previous generated schedules so a retry
    # always uses the currently doctor-confirmed data.
    schedule_ids = select(
        MedicationSchedule.id
    ).where(
        MedicationSchedule.consultation_id == cid
    )

    await db.execute(
        delete(MedicationEvent).where(
            MedicationEvent.schedule_id.in_(
                schedule_ids
            )
        )
    )

    await db.execute(
        delete(MedicationSchedule).where(
            MedicationSchedule.consultation_id
            == cid
        )
    )

    await db.flush()

    from app.api.schedules import (
        generate_for_consultation,
    )

    schedules = await generate_for_consultation(
        db,
        c,
        doctor.id,
    )

    generated = {
        s["consultation_medication_id"]: s
        for s in schedules
    }

    # A fixed medication MUST have real reminder events.
    for med in fixed_meds:
        schedule = generated.get(med.id)

        if (
            not schedule
            or not schedule.get("events")
        ):
            name = (
                med.canonical_name
                or med.raw_name
                or "Medication"
            )

            raise HTTPException(
                status.HTTP_409_CONFLICT,
                (
                    f"Release stopped because the "
                    f"reminder timetable for {name} "
                    "could not be generated."
                ),
            )

    # Make the doctor-confirmed DB medication rows
    # the patient-facing source as well.
    await _sync_confirmed_medications(
        db,
        c,
    )

    # Only NOW is the patient allowed to receive it.
    c.status = ConsultationStatus.RELEASED
    c.released_at = datetime.utcnow()

    await audit(
        db,
        doctor.id,
        "consultation.released",
        "consultation",
        cid,
        {
            "schedules": len(schedules),
            "fixed_medications": len(fixed_meds),
        },
    )

    return c
@router.get("/{cid}/audio-summary")
async def audio_summary(
    cid: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = await _load(db, cid)
    await require_can_view_consultation(db, user, c)

    if user.role == UserRole.PATIENT:
        require_released(c)

    p = resolve_storage_ref(c.audio_summary_path)

    if not p or not p.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No audio available",
        )

    await audit(
        db,
        user.id,
        "consultation.audio_accessed",
        "consultation",
        cid,
    )

    media = (
        mimetypes.guess_type(p.name)[0]
        or "audio/wav"
    )

    return FileResponse(
        p,
        media_type=media,
        filename=p.name,
    )

async def audio_summary(
    cid:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)
):
    c=await _load(db,cid);await require_can_view_consultation(db,user,c)
    if user.role==UserRole.PATIENT:require_released(c)
    p=resolve_storage_ref(c.audio_summary_path)
    if not p or not p.exists():raise HTTPException(status.HTTP_404_NOT_FOUND,"No audio available")
    await audit(db,user.id,"consultation.audio_accessed","consultation",cid)
    media=mimetypes.guess_type(p.name)[0] or "audio/wav"
    return FileResponse(p,media_type=media,filename=p.name)

@router.get("/{cid}/pdf")
async def download_pdf(
    cid:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)
):
    c=await _load(db,cid);await require_can_view_consultation(db,user,c)
    if user.role==UserRole.PATIENT:require_released(c)
    patient=(await db.execute(select(User).where(User.id==c.patient_id))).scalar_one()
    doctor=(await db.execute(select(User).where(User.id==c.doctor_id))).scalar_one()
    out=settings.UPLOAD_DIR/f"care_summary_{c.id}_{c.patient_language}.pdf"
    schedules = await pdf_export.schedule_payload(db, c.id)
    medications = await pdf_export.medication_payload(db, c.id)
    await asyncio.to_thread(pdf_export.generate_patient_pdf,c,patient,doctor,out,schedules,medications)
    await audit(db,user.id,"consultation.pdf_downloaded","consultation",cid)
    return FileResponse(out,media_type="application/pdf",filename=f"care_summary_{c.id}.pdf")

@router.post("/{cid}/whatsapp-pdf")
async def send_whatsapp_pdf(
    cid:int,phone:str|None=Query(None),
    db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)
):
    """Send the exact released portal PDF as a WhatsApp document when configured."""
    c=await _load(db,cid);require_owner_doctor(user,c);require_released(c)
    target=phone or c.patient_phone
    try:
        normalised=whatsapp_svc.normalise_phone(target)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,str(exc)) from exc

    # Keep the number on the consultation only when the treating doctor supplied it.
    if phone:
        c.patient_phone=phone.strip()

    patient=(await db.execute(select(User).where(User.id==c.patient_id))).scalar_one()
    doctor=(await db.execute(select(User).where(User.id==c.doctor_id))).scalar_one()
    schedules=await pdf_export.schedule_payload(db,c.id)
    medications=await pdf_export.medication_payload(db,c.id)
    out=settings.UPLOAD_DIR/f"care_summary_{c.id}_{c.patient_language}.pdf"
    await asyncio.to_thread(
        pdf_export.generate_patient_pdf,c,patient,doctor,out,schedules,medications
    )
    try:
        result=await whatsapp_svc.send_pdf(
            normalised,out.read_bytes(),f"care_summary_{c.id}.pdf",
            f"MediExplain+ released patient summary · Consultation #{c.id}",
        )
    except Exception as exc:
        logger.warning("WhatsApp delivery failed for consultation %s: %s",cid,exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,f"WhatsApp delivery failed: {exc}") from exc

    await audit(db,user.id,"consultation.whatsapp_pdf_sent","consultation",cid,{
        "message_id":result.get("message_id"),"recipient_suffix":normalised[-4:],
    })
    return {
        "sent":True,"message_id":result.get("message_id"),
        "patient_phone":normalised,"filename":f"care_summary_{c.id}.pdf",
    }


@router.post("/{cid}/share",response_model=ShareLink)
async def create_share_link(
    cid:int,phone:str|None=Query(None),
    db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)
):
    c=await _load(db,cid);require_owner_doctor(user,c);require_released(c)
    url=share_svc.share_url(c.id)
    wa=share_svc.whatsapp_link(c.id,phone or c.patient_phone,language=c.patient_language)
    await audit(db,user.id,"consultation.share_created","consultation",cid)
    return ShareLink(share_url=url,whatsapp_url=wa,expires_in_hours=settings.SHARE_TOKEN_EXPIRE_HOURS)

@router.post("/{cid}/consent/withdraw",response_model=ConsultationPublic)
async def withdraw_consent(
    cid:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)
):
    c=await _load(db,cid)
    if user.role==UserRole.PATIENT:require_patient_owner(user,c)
    else:require_owner_doctor(user,c)
    record=(await db.execute(select(ConsentRecord).where(ConsentRecord.consultation_id==cid))).scalar_one_or_none()
    if record:
        record.withdrawn_at=datetime.utcnow();record.withdrawn_by_id=user.id
    # Stop future processing and remove raw consultation audio immediately.
    safe_unlink(c.audio_path);c.audio_path=None;c.status=ConsultationStatus.REJECTED
    await audit(db,user.id,"consent.withdrawn","consultation",cid)
    return c

@router.delete("/{cid}",status_code=204)
async def delete_consultation(
    cid:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)
):
    c=await _load(db,cid)
    if user.role==UserRole.PATIENT:require_patient_owner(user,c)
    else:require_owner_doctor(user,c)

    # Collect files before deleting rows.
    refs=[c.audio_path,c.audio_summary_path,c.prescription_image_path]
    p=(await db.execute(select(Prescription).where(Prescription.consultation_id==cid))).scalar_one_or_none()
    if p:refs.append(p.image_path)
    events=list((await db.execute(
        select(MedicationEvent).join(MedicationSchedule,MedicationEvent.schedule_id==MedicationSchedule.id)
        .where(MedicationSchedule.consultation_id==cid)
    )).scalars())
    refs.extend(e.reminder_audio_path for e in events)

    # Explicit deletes make erasure deterministic even if SQLite FK cascade is disabled.
    schedule_ids=select(MedicationSchedule.id).where(MedicationSchedule.consultation_id==cid)
    for model,clause in (
        (MedicationEvent,MedicationEvent.schedule_id.in_(schedule_ids)),
        (MedicationSchedule,MedicationSchedule.consultation_id==cid),
        (ConsultationMedication,ConsultationMedication.consultation_id==cid),
        (TranslationRecord,TranslationRecord.consultation_id==cid),
        (Prescription,Prescription.consultation_id==cid),
        (SafetyCheck,SafetyCheck.consultation_id==cid),
        (SummaryVersion,SummaryVersion.consultation_id==cid),
        (TranscriptSegment,TranscriptSegment.consultation_id==cid),
        (ConsentRecord,ConsentRecord.consultation_id==cid),
        (CrossCheck,CrossCheck.consultation_id==cid),
    ):
        await db.execute(delete(model).where(clause))
    await db.execute(delete(Consultation).where(Consultation.id==cid))
    # Preserve minimal audit evidence without medical content.
    await audit(db,user.id,"consultation.deleted","consultation",cid,{"erasure":"derived clinical artifacts removed"})
    await db.flush()
    for ref in refs:safe_unlink(ref)
    # Generated PDFs are deterministic derived artifacts.
    for f in settings.UPLOAD_DIR.glob(f"*{cid}*.pdf"):f.unlink(missing_ok=True)
    return None
