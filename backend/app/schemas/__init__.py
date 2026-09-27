"""Pydantic API contracts for MediExplain+ Final."""
from datetime import date, datetime
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.user import UserRole
from app.models.consultation import ConsultationStatus

# This schema defines the information required when a normal user account is created,
# including the login details, display name and preferred language.
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    preferred_language: str = "en"

# This extends the normal user creation schema for administrator-created accounts.
# It also allows the administrator to assign the user's role and clinical details.
class AdminUserCreate(UserCreate):
    role: UserRole
    specialty: Optional[str] = None
    clinic: Optional[str] = None

# This is the public representation of a MediExplain+ user returned by the API.
# It exposes profile, role and verification information without returning password data.
class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    preferred_language: str
    specialty: Optional[str] = None
    clinic: Optional[str] = None
    is_verified: bool = False
    mfa_enabled: bool = False

# This schema defines the successful authentication response sent back to the client,
# containing the application access token together with the authenticated user profile.
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# This schema contains the information required to create a new consultation,
# including the patient, consent details, selected language and optional STT languages.
class ConsultationCreate(BaseModel):
    patient_id: int
    doctor_consent: bool
    patient_consent: bool
    consent_method: str = "verbal"
    patient_language: str = "en"
    stt_primary_language: Optional[str] = None
    stt_secondary_language: Optional[str] = None

# This structure represents one medication extracted or entered during a consultation.
# It keeps the medicine name, dose and instructions together with extraction confidence,
# possible terminology matches and the final doctor-confirmation state.
class MedicationStructured(BaseModel):
    name: str = ""
    name_as_heard: str = ""
    confidence: float = 0.0
    dose: Optional[str] = None
    strength: Optional[str] = None
    dose_unit: Optional[str] = None
    dosage_form: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    timing: Optional[str] = None
    food_instruction: Optional[str] = None
    duration: Optional[str] = None
    as_needed: bool = False
    indication: Optional[str] = None
    notes: Optional[str] = None
    doctor_confirmed: bool = False
    suggestions: list[dict[str, Any]] = Field(default_factory=list)


# This schema organises the structured clinical information produced from a consultation.
# It separates symptoms, history, discussed diagnoses, medications, tests, advice,
# follow-up information and warning signs so they can be reviewed independently.
class StructuredData(BaseModel):
    chief_complaint: Optional[str] = None
    symptoms: list[str] = Field(default_factory=list)
    relevant_history: list[str] = Field(default_factory=list)
    diagnosis_discussed: list[str] = Field(default_factory=list)
    diagnosis_status: Optional[str] = None
    medications: list[MedicationStructured] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    follow_up: Optional[str] = None
    warning_signs: list[str] = Field(default_factory=list)
    glossary: list[dict[str, str]] = Field(default_factory=list)

# This is the patient/doctor-facing API representation of an individual transcript
# segment. It includes the original STT text, reviewed text, timing, language and
# confidence information needed to identify parts of the transcript requiring review.
class TranscriptSegmentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    segment_index: int
    start_seconds: float
    end_seconds: float
    text_raw: str
    text_reviewed: Optional[str] = None
    language: Optional[str] = None
    confidence: Optional[float] = None
    avg_logprob: Optional[float] = None
    no_speech_prob: Optional[float] = None
    speaker_label: Optional[str] = None
    diarization_confidence: Optional[float] = None
    needs_review: bool = False

# This schema defines the transcript fields that can be changed during manual review,
# allowing reviewed wording, speaker labels and the review flag to be updated.
class TranscriptSegmentUpdate(BaseModel):
    text_reviewed: Optional[str] = None
    speaker_label: Optional[str] = None
    needs_review: Optional[bool] = None

# This schema exposes the result of an individual consultation safety check.
# It keeps the check type, outcome, severity, evidence and score together with
# whether the issue has already been resolved by a clinician.
class SafetyCheckPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    check_type: str
    status: str
    severity: str
    statement: Optional[str] = None
    evidence: Optional[str] = None
    score: Optional[float] = None
    details: Optional[dict] = None
    resolved: bool

# This is the main consultation response returned through the API. It combines the
# consultation status with transcript data, generated clinical and patient summaries,
# structured information, translation results, OCR output and approval/release details.
# Model metadata is also exposed here so outputs produced by the AI pipeline can retain
# information about the models and processing stages that generated them.

class ConsultationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doctor_id: int
    patient_id: int
    status: ConsultationStatus
    patient_language: str
    raw_transcript: Optional[str] = None
    transcript_normalised: Optional[str] = None
    verified_transcript: Optional[str] = None
    languages_detected: Optional[list[str] | dict] = None
    code_switched: bool = False
    stt_primary_language: Optional[str] = None
    stt_secondary_language: Optional[str] = None
    clinical_note: Optional[str] = None
    patient_summary_en: Optional[str] = None
    patient_summary_translated: Optional[str] = None
    structured_data: Optional[dict] = None
    audio_summary_path: Optional[str] = None
    tts_backend: Optional[str] = None
    doctor_edited_summary: Optional[str] = None
    translation_quality: Optional[str] = None
    translation_verified: bool = False
    dose_sentences_for_review: Optional[list[str] | dict] = None
    prescription_ocr_text: Optional[str] = None
    prescription_ocr_confidence: Optional[float] = None
    patient_phone: Optional[str] = None
    approved_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    pipeline_error: Optional[str] = None
    model_metadata: Optional[dict] = None
    created_at: datetime

# This schema represents the result returned by prescription OCR processing.
# It includes the recognised text, OCR confidence and engine together with any
# warning or structured information extracted from the prescription.
class OCRResult(BaseModel):
    text: str
    confidence: float
    available: bool
    engine: Optional[str] = None
    warning: Optional[str] = None
    structured: Optional[dict] = None


# This request schema is used when a doctor manually corrects the text produced
# by prescription OCR before the information is used further in the workflow.
class OCRCorrection(BaseModel):
    text: str = Field(min_length=1)

# This schema contains the temporary patient-sharing links created for a released
# consultation, including the normal share URL, WhatsApp URL and expiry period.
class ShareLink(BaseModel):
    share_url: str
    whatsapp_url: str
    expires_in_hours: int

# This defines the restricted information available through a public share link.
# It exposes the released patient summary and delivery information without exposing
# the full internal consultation record.
class PublicShareView(BaseModel):
    id: int
    patient_language: str
    patient_summary: str
    structured_data: Optional[dict] = None
    has_audio: bool
    has_pdf: bool

# This schema is used when the treating doctor performs the final approval step.
# The doctor can provide an edited patient summary and explicitly confirm approval.
class DoctorApproval(BaseModel):
    edited_summary: Optional[str] = None
    approve: bool = True

# This request creates a second-opinion cross-check for a consultation by identifying
# the consultation, the selected reviewer and an optional reason for requesting it.
class CrossCheckCreate(BaseModel):
    consultation_id: int
    reviewer_id: int
    reason: Optional[str] = None

# This schema contains the decision submitted by the cross-check doctor together
# with optional comments explaining their review of the released consultation
class CrossCheckSubmit(BaseModel):
    verdict: str = Field(pattern="^(agree|partially_agree|disagree|suggest_followup|flag)$")
    comments: Optional[str] = None


# This is the API representation of a cross-check request and its outcome. It keeps
# the assigned reviewer, requester, current review status, verdict, comments and
# completion information so the second-opinion process remains traceable.
class CrossCheckPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    consultation_id: int
    reviewer_id: int
    requester_id: Optional[int] = None
    request_status: str = "pending"
    reason: Optional[str] = None
    verdict: str
    comments: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

# This schema defines the medication fields that a doctor can edit or confirm during
# medication reconciliation. Identity and instruction confirmation are kept separate
# so both the medicine itself and its patient-specific directions can be reviewed.
class MedicationUpdate(BaseModel):
    name: Optional[str] = None
    concept_id: Optional[int] = None
    dose: Optional[str] = None
    strength: Optional[str] = None
    dose_unit: Optional[str] = None
    dosage_form: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    timing: Optional[str] = None
    food_instruction: Optional[str] = None
    duration: Optional[str] = None
    as_needed: Optional[bool] = None
    indication: Optional[str] = None
    notes: Optional[str] = None
    confirm_identity: bool = False
    confirm_instructions: bool = False

# This represents one medication reminder event returned to the patient.
# It records when the reminder is scheduled and whether it was taken, skipped,
# snoozed or acted on at another recorded time.
class ScheduleEventPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    schedule_id: int
    scheduled_at: datetime
    status: str
    action_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None

# This schema represents a complete patient medication schedule. It combines the
# confirmed medicine and instructions with the active date range, timezone and
# individual reminder events generated for that schedule.
class SchedulePublic(BaseModel):
    id: int
    consultation_id: int
    consultation_medication_id: int
    patient_id: int
    medication_name: str
    dose: Optional[str] = None
    instructions: Optional[str] = None
    timezone: str
    start_date: date
    end_date: Optional[date] = None
    active: bool
    events: list[ScheduleEventPublic] = Field(default_factory=list)

# This request records how the patient responds to a medication reminder.
# Supported actions are taken, skipped or snoozed, with a controlled snooze period.
class EventAction(BaseModel):
    action: str = Field(pattern="^(taken|skip|snooze)$")
    snooze_minutes: int = Field(default=15, ge=1, le=240)


# ---------------------------------------------------------------------------
# Additive delegated assistant review + support/help contracts
# ---------------------------------------------------------------------------

# This request is used by a doctor to delegate a consultation for assistant
# pre-review by identifying both the consultation and the assigned assistant.
class AssistantReviewCreate(BaseModel):
    consultation_id: int
    assistant_id: int

# This schema contains the assistant's completed pre-review information,
# including the checklist result, review notes and whether the case was checked.

class AssistantReviewSubmit(BaseModel):
    checked: bool
    notes: Optional[str] = Field(default=None, max_length=4000)
    checklist: dict[str, bool] = Field(default_factory=dict)

# This is the public representation of an assistant review assignment. It keeps
# the people involved, review status, checklist, notes and assignment/completion
# times without giving the assistant final approval or release authority.
class AssistantReviewPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    consultation_id: int
    assistant_id: int
    assigned_by_id: int
    status: str
    checklist: Optional[dict] = None
    notes: Optional[str] = None
    checked: bool
    assigned_at: datetime
    checked_at: Optional[datetime] = None


# This schema provides the information an assigned assistant needs to review a case.
# It combines the review assignment with the relevant consultation, transcript,
# summaries, medication rows and safety checks in one restricted response.
class AssistantReviewCase(BaseModel):
    review: AssistantReviewPublic
    consultation_id: int
    doctor_id: int
    patient_id: int
    patient_language: str
    status: ConsultationStatus
    raw_transcript: Optional[str] = None
    verified_transcript: Optional[str] = None
    patient_summary_en: Optional[str] = None
    patient_summary_translated: Optional[str] = None
    doctor_edited_summary: Optional[str] = None
    structured_data: Optional[dict] = None
    medication_rows: list[dict] = Field(default_factory=list)
    safety_checks: list[SafetyCheckPublic] = Field(default_factory=list)

# This schema validates new privacy, security, technical and general support tickets.
# It controls the permitted categories and urgency values and also supports specific
# privacy-request types when a user contacts the MediExplain+ support workflow.
class SupportTicketCreate(BaseModel):
    category: str = Field(pattern="^(data_breach|technical_problem|help_request|contact)$")
    subject: str = Field(min_length=3, max_length=255)
    message: str = Field(min_length=10, max_length=10000)
    contact_email: Optional[EmailStr] = None
    urgency: str = Field(default="normal", pattern="^(normal|high|critical)$")
    privacy_request_type: Optional[str] = Field(
        default=None,
        pattern=(
            "^(general_support|access_copy|amend_information|"
            "restrict_use_disclosure|confidential_communication|"
            "accounting_disclosures|withdraw_consent|delete_data|"
            "privacy_complaint|security_incident|other_privacy_request)$"
        ),
    )

# This is the API representation of a submitted support ticket. It returns the
# reporter, request details, contact information, urgency, current status and
# creation time so users and administrators can follow the request.
class SupportTicketPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reporter_id: int
    category: str
    subject: str
    message: str
    contact_email: Optional[str] = None
    urgency: str
    privacy_request_type: Optional[str] = None
    status: str
    created_at: datetime
