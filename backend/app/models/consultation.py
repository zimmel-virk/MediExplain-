"""Consultation, consent, transcript, safety, medication and review data models."""
import enum
from datetime import date, datetime
from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.base import Base

# This file defines the main database structure behind the MediExplain+ consultation
# workflow. It stores the consultation lifecycle from recording through transcript
# review, safety checking, doctor approval, release and optional cross-checking, along
# with consent records and individual transcript segments. It also keeps versioned
# clinical notes and patient summaries, including their source and model information
# when an AI-generated version is saved, so later doctor-edited and approved versions
# can be distinguished from earlier outputs. The remaining models hold safety-check
# results, prescription OCR data, medication terminology and aliases, confirmed
# consultation medicines, reminder schedules and events, translation verification
# records, and second-opinion reviews. Foreign keys, unique constraints and cascade
# rules keep these records tied to the correct consultation while preserving the
# information needed for clinical review, auditing and patient delivery.



# These values represent the different stages a consultation can move through,
# starting from recording and transcription and continuing through review,
# safety checking, doctor approval, patient release and optional cross-checking.

class ConsultationStatus(str, enum.Enum):
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    TRANSCRIPT_REVIEW = "transcript_review"
    SUMMARISING = "summarising"
    SAFETY_CHECK = "safety_check"
    DRAFTED = "drafted"
    SAFETY_REVIEW_REQUIRED = "safety_review_required"
    APPROVED = "approved"
    TRANSLATING = "translating"
    RELEASED = "released"
    UNDER_CROSS_CHECK = "under_cross_check"
    CROSS_CHECKED = "cross_checked"
    REJECTED = "rejected"
    PROCESSING_FAILED = "processing_failed"

# This is the main consultation record and connects most parts of the MediExplain+
# workflow. It stores the doctor and patient involved, consultation audio and
# transcript information, generated clinical and patient summaries, translation
# results, prescription information and the current workflow status. It also keeps
# model metadata so AI-generated outputs can be traced to the model/process that
# produced them before they are reviewed and approved by the doctor.
class Consultation(Base):
    __tablename__ = "consultations"
        # SQLite normally allows INTEGER PRIMARY KEY values to be reused
    # after deletion. Audit logs survive consultation erasure, so a
    # reused ID could incorrectly join historical audit events to a
    # later consultation.
    #
    # This affects newly-created databases. Existing databases are
    # additionally protected by the application-level allocator below.
    __table_args__ = {
        "sqlite_autoincrement": True,
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Legacy flags retained for backwards compatibility; ConsentRecord is source of truth.
    doctor_consent: Mapped[bool] = mapped_column(default=False)
    patient_consent: Mapped[bool] = mapped_column(default=False)

    audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    raw_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_normalised: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    languages_detected: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    code_switched: Mapped[bool] = mapped_column(Boolean, default=False)
    stt_primary_language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    stt_secondary_language: Mapped[str | None] = mapped_column(String(8), nullable=True)

    clinical_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_summary_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_summary_translated: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_language: Mapped[str] = mapped_column(String(8), default="en")
    structured_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    translation_quality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dose_sentences_for_review: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    translation_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    audio_summary_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tts_backend: Mapped[str | None] = mapped_column(String(32), nullable=True)

    prescription_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    prescription_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    prescription_ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    patient_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[ConsultationStatus] = mapped_column(
        Enum(ConsultationStatus), default=ConsultationStatus.RECORDING
    )

    doctor_edited_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    pipeline_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    cross_checks: Mapped[list["CrossCheck"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )

# This class keeps the consent information for each consultation separately from
# the main consultation record. It records whether both the doctor and patient
# agreed, how the consent was obtained, which consent version was used and whether
# that consent was later withdrawn.
class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), unique=True
    )
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    doctor_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    patient_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    method: Mapped[str] = mapped_column(String(32), default="verbal")
    consent_version: Mapped[str] = mapped_column(String(32), default="1.0")
    granted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    withdrawn_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

# This class stores the consultation transcript in smaller timed segments instead
# of keeping only one large block of text. Each segment can keep the original and
# reviewed wording, detected language, STT confidence information, speaker details
# and a flag showing whether the segment needs manual review.
class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("consultation_id", "segment_index", name="uq_transcript_segment"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), index=True
    )
    segment_index: Mapped[int] = mapped_column(Integer)
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    text_raw: Mapped[str] = mapped_column(Text)
    text_reviewed: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    language_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_logprob: Mapped[float | None] = mapped_column(Float, nullable=True)
    no_speech_prob: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    speaker_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    diarization_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

# This class keeps a version history of clinical notes and patient summaries.
# AI-generated versions can be stored with their model name and source, while later
# doctor-edited versions are kept separately. This makes it possible to trace how
# a summary changed before the final version was approved.
class SummaryVersion(Base):
    __tablename__ = "summary_versions"
    __table_args__ = (
        UniqueConstraint("consultation_id", "kind", "version", name="uq_summary_version"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # clinical_note | patient_summary
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="ai")
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

# This class stores the result of each safety check carried out on a consultation.
# It records the type of check, whether it passed or produced a warning/failure,
# supporting evidence and scores, and whether a clinician later resolved the issue.
# This allows safety warnings from automated checks to remain visible and auditable
# before the consultation is approved.
class SafetyCheck(Base):
    __tablename__ = "safety_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), index=True
    )
    check_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16))  # pass/warning/fail/unavailable
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

# This class stores prescription-processing information linked to a consultation.
# It keeps the uploaded prescription image, the text extracted by OCR, any corrected
# version of that text, the OCR engine and confidence, structured medication data
# and whether the extracted prescription information was confirmed by the doctor.
class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), unique=True
    )
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_engine: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    structured_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    doctor_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

# This class represents an individual medication entry in the local medication
# terminology database. It stores the normalised medicine name together with
# information such as generic and brand names, strength, dosage form, route,
# active ingredient, manufacturer and the external source it came from.
class MedicationConcept(Base):
    __tablename__ = "medication_concepts"
    __table_args__ = (
        UniqueConstraint("source", "source_id", "display_name", name="uq_medication_concept_source_display"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(512), index=True)
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)
    tty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    generic_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(String(128), nullable=True)
    route: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active_ingredient: Mapped[str | None] = mapped_column(String(512), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# This class stores alternative names or synonyms for medication concepts.
# Different spellings, brand names or other aliases can therefore be linked back
# to the same medication entry, helping the medication matching process recognise
# different ways the same medicine may appear in a transcript or prescription.
class MedicationAlias(Base):
    __tablename__ = "medication_aliases"
    __table_args__ = (
        UniqueConstraint("concept_id", "normalized_alias", name="uq_med_alias"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("medication_concepts.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(512))
    normalized_alias: Mapped[str] = mapped_column(String(512), index=True)
    alias_type: Mapped[str] = mapped_column(String(32), default="synonym")

# This class stores the medication information that belongs to one consultation.
# It keeps both the originally extracted medicine wording and the matched canonical
# medication details, together with dose, strength, route, frequency, duration and
# other instructions. Extraction and matching confidence values are preserved so
# uncertain AI/extraction results can be reviewed before the doctor confirms them.
class ConsultationMedication(Base):
    __tablename__ = "consultation_medications"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(24), default="transcript")
    source_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    concept_id: Mapped[int | None] = mapped_column(
        ForeignKey("medication_concepts.id"), nullable=True
    )
    canonical_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    generic_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dose: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dose_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(String(128), nullable=True)
    route: Mapped[str | None] = mapped_column(String(128), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timing: Mapped[str | None] = mapped_column(String(128), nullable=True)
    food_instruction: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration: Mapped[str | None] = mapped_column(String(128), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    as_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    indication: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    doctor_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    discrepancy_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

# This class represents a doctor-confirmed medication schedule for a patient.
# It links the confirmed consultation medication to the patient and stores the
# schedule dates, timezone and instructions used to create medication reminders.
class MedicationSchedule(Base):
    __tablename__ = "medication_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), index=True
    )
    consultation_medication_id: Mapped[int] = mapped_column(
        ForeignKey("consultation_medications.id", ondelete="CASCADE"), index=True
    )
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Karachi")
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# This class represents an individual reminder generated from a medication
# schedule. It stores when the reminder should occur, whether it is still pending
# or has been acted on, any snooze time and the generated reminder-audio reference.
class MedicationEvent(Base):
    __tablename__ = "medication_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("medication_schedules.id", ondelete="CASCADE"), index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    action_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reminder_audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)


# This class keeps a record of patient-facing translations produced for a
# consultation. Along with the translated text, it stores the translation model
# used and the results of checks for number preservation, medication-name
# preservation, script validity and semantic consistency.
class TranslationRecord(Base):
    __tablename__ = "translation_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[str] = mapped_column(String(16))
    source_hash: Mapped[str] = mapped_column(String(64))
    translated_text: Mapped[str] = mapped_column(Text)
    back_translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    numeric_preserved: Mapped[bool] = mapped_column(Boolean, default=False)
    medication_preserved: Mapped[bool] = mapped_column(Boolean, default=False)
    script_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    semantic_status: Mapped[str] = mapped_column(String(16), default="unavailable")
    semantic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

# This class manages the second-opinion or cross-check process for a consultation.
# It records which verified reviewer received the case, who requested the review,
# its current status, the reason for the request, the reviewer's verdict and
# comments, and when the cross-check was completed.
class CrossCheck(Base):
    __tablename__ = "cross_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(ForeignKey("consultations.id"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    requester_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    request_status: Mapped[str] = mapped_column(String(24), default="pending")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict: Mapped[str] = mapped_column(String(32), default="pending")
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, server_default=func.now(), onupdate=func.now()
    )

    consultation: Mapped["Consultation"] = relationship(back_populates="cross_checks")
