"""/api/schedules — doctor-confirmed medication schedules and patient reminders."""

# This file manages the medication schedule and reminder workflow in MediExplain+.
# It creates schedules only from medication instructions that have already been
# confirmed by the doctor and converts those instructions into individual reminder
# events for the patient. It also handles timezone-aware dates and times, allows
# patients to mark reminders as taken, snoozed or skipped, and keeps these actions
# recorded in the audit trail. For voice reminders, the patient-facing instructions
# can be translated into the selected language while the confirmed medication name
# is kept unchanged. Reminder audio is generated when needed and then cached for
# later use, with the appropriate TTS route selected for the supported languages.
# Access to schedules and reminder audio is restricted to the relevant consultation
# and patient so medication information is not exposed to unrelated users.

from __future__ import annotations
from app.services import reminder_voice
from app.services import tts as production_tts

import asyncio
import mimetypes

from datetime import (
    datetime,
    timedelta,
)

from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from fastapi.responses import (
    FileResponse,
)

from sqlalchemy import (
    select,
)

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.core.audit import audit

from app.core.authorization import (
    require_can_view_consultation,
    require_owner_doctor,
    require_released,
)

from app.core.config import settings

from app.core.database import (
    get_db,
)

from app.core.security import (
    get_current_user,
)

from app.core.storage import (
    resolve_storage_ref,
    to_storage_ref,
)

from app.models import (
    Consultation,
    ConsultationMedication,
    MedicationEvent,
    MedicationSchedule,
    User,
    UserRole,
)

from app.schemas import (
    EventAction,
)

from app.services import (
    scheduler,
    translation,
    tts,
)


router = APIRouter(
    prefix="/api/schedules",
    tags=[
        "medication-schedules"
    ],
)


# ---------------------------------------------------------
# DATE/TIME HELPERS
# ---------------------------------------------------------

def _timezone(
    timezone: str | None,
) -> ZoneInfo:
    return ZoneInfo(
        timezone
        or settings.DEFAULT_TIMEZONE
    )


def _aware_iso(
    value: datetime | None,
    timezone: str | None,
) -> str | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=_timezone(
                timezone
            )
        )

    return value.isoformat()


def _spoken_date(
    value: datetime,
) -> str:
    return value.strftime(
        "%A, %d %B %Y"
    )


def _spoken_time(
    value: datetime,
) -> str:
    return (
        value.strftime(
            "%I:%M %p"
        )
        .lstrip("0")
    )


# ---------------------------------------------------------
# API SERIALISATION
# ---------------------------------------------------------

def _schedule_dict(
    schedule: MedicationSchedule,
    med: ConsultationMedication,
    events: list[MedicationEvent],
) -> dict:
    timezone = (
        schedule.timezone
        or settings.DEFAULT_TIMEZONE
    )

    return {
        "id":
            schedule.id,

        "consultation_id":
            schedule.consultation_id,

        "consultation_medication_id":
            schedule
            .consultation_medication_id,

        "patient_id":
            schedule.patient_id,

        "medication_name":
            (
                med.canonical_name
                or med.raw_name
                or "Medication"
            ),

        "raw_medication_name":
            med.raw_name,

        "dose":
            (
                med.dose
                or med.strength
            ),

        "strength":
            med.strength,

        "dose_unit":
            med.dose_unit,

        "dosage_form":
            med.dosage_form,

        "route":
            med.route,

        "frequency":
            med.frequency,

        "timing":
            med.timing,

        "food_instruction":
            med.food_instruction,

        "duration":
            med.duration,

        "as_needed":
            bool(
                med.as_needed
            ),

        "instructions":
            schedule.instructions,

        "timezone":
            timezone,

        "start_date":
            (
                schedule.start_date
                .isoformat()
                if schedule.start_date
                else None
            ),

        "end_date":
            (
                schedule.end_date
                .isoformat()
                if schedule.end_date
                else None
            ),

        "active":
            schedule.active,

        "events": [
            {
                "id":
                    event.id,

                "schedule_id":
                    event.schedule_id,

                "scheduled_at":
                    _aware_iso(
                        event.scheduled_at,
                        timezone,
                    ),

                "status":
                    event.status,

                "action_at":
                    _aware_iso(
                        event.action_at,
                        timezone,
                    ),

                "snoozed_until":
                    _aware_iso(
                        event.snoozed_until,
                        timezone,
                    ),

                "voice_cached":
                    bool(
                        event
                        .reminder_audio_path
                    ),
            }
            for event in events
        ],
    }


# ---------------------------------------------------------
# REMINDER TEXT
# ---------------------------------------------------------

def _reminder_components(
    med: ConsultationMedication,
    scheduled_at: datetime,
) -> tuple[
    str,
    str,
    str,
]:
    med_name = (
        med.canonical_name
        or med.raw_name
        or "your medication"
    )

    date_text = _spoken_date(
        scheduled_at
    )

    time_text = _spoken_time(
        scheduled_at
    )

    # Prefix/suffix are translated separately so the
    # medication name itself remains exactly recognisable.
    prefix = (
        "Medication reminder. "
        f"Today is {date_text}. "
        f"The medication time is {time_text}. "
        "Please take"
    )

    details = []

    if (
        med.dose
        or med.strength
    ):
        details.append(
            "Dose or quantity: "
            f"{med.dose or med.strength}."
        )

    if med.frequency:
        details.append(
            "Frequency: "
            f"{med.frequency}."
        )

    if med.timing:
        details.append(
            "Timing instruction: "
            f"{med.timing}."
        )

    if med.food_instruction:
        details.append(
            "Food instruction: "
            f"{med.food_instruction}."
        )

    if med.duration:
        details.append(
            "Duration: "
            f"{med.duration}."
        )

    if med.route:
        details.append(
            "Route: "
            f"{med.route}."
        )

    details.append(
        "After taking the medicine, "
        "mark this reminder as taken."
    )

    suffix = " ".join(
        details
    )

    return (
        prefix,
        med_name,
        suffix,
    )


async def _spoken_reminder(
    consultation: Consultation,
    med: ConsultationMedication,
    scheduled_at: datetime,
) -> tuple[
    str,
    str | None,
]:
    (
        prefix,
        med_name,
        suffix,
    ) = _reminder_components(
        med,
        scheduled_at,
    )

    target = (
        consultation.patient_language
        or "en"
    )

    full_english = (
        f"{prefix} "
        f"{med_name}. "
        f"{suffix}"
    )

    if target == "en":
        return (
            full_english,
            None,
        )

    # Translate instructions but preserve the actual
    # doctor-confirmed medication name.
    translated_prefix = (
        await asyncio.to_thread(
            translation.translate,
            prefix,
            "en",
            target,
        )
    )

    translated_suffix = (
        await asyncio.to_thread(
            translation.translate,
            suffix,
            "en",
            target,
        )
    )

    spoken = (
        f"{translated_prefix} "
        f"{med_name}. "
        f"{translated_suffix}"
    )

    alternate = None

    if target == "pa_shah":
        # Internal Gurmukhi input may be used by the Punjabi
        # voice backend, but it is never shown to the patient.
        alternate = (
            await asyncio.to_thread(
                translation.translate_nllb,
                full_english,
                "en",
                "pa",
            )
        )

    return (
        spoken,
        alternate,
    )


# ---------------------------------------------------------
# LAZY VOICE CACHE
# ---------------------------------------------------------

async def _ensure_event_audio(
    db: AsyncSession,
    consultation: Consultation,
    schedule: MedicationSchedule,
    med: ConsultationMedication,
    event: MedicationEvent,
):
    existing = resolve_storage_ref(
        event.reminder_audio_path
    )

    if (
        existing
        and existing.exists()
    ):
        return existing

    scheduled_at = (
        event.snoozed_until
        if (
            event.status
            == "snoozed"
            and event.snoozed_until
        )
        else event.scheduled_at
    )

    if scheduled_at is None:
        raise RuntimeError(
            "Reminder event has no scheduled time."
        )

    spoken, alternate = (
        await _spoken_reminder(
            consultation,
            med,
            scheduled_at,
        )
    )

    voice_synthesiser = (
        production_tts.synthesise
        if consultation.patient_language
        in {"ar", "ps", "sd"}
        else reminder_voice.synthesise
    )

    audio = (
        await asyncio.to_thread(
            voice_synthesiser,
            spoken,
            consultation.patient_language,
            alternate,
        )
    )

    if not audio:
        raise RuntimeError(
            "Text-to-speech did not produce audio."
        )

    event.reminder_audio_path = (
        to_storage_ref(
            audio
        )
    )

    await db.flush()

    return resolve_storage_ref(
        event.reminder_audio_path
    )


# ---------------------------------------------------------
# GENERATE SCHEDULES
# ---------------------------------------------------------

async def generate_for_consultation(
    db: AsyncSession,
    consultation: Consultation,
    actor_id: int,
) -> list[dict]:
    meds = list(
        (
            await db.execute(
                select(
                    ConsultationMedication
                )
                .where(
                    ConsultationMedication
                    .consultation_id
                    == consultation.id,

                    ConsultationMedication
                    .doctor_confirmed
                    .is_(True),
                )
                .order_by(
                    ConsultationMedication.id
                )
            )
        ).scalars()
    )

    results = []

    for med in meds:
        existing = (
            await db.execute(
                select(
                    MedicationSchedule
                ).where(
                    MedicationSchedule
                    .consultation_medication_id
                    == med.id
                )
            )
        ).scalar_one_or_none()

        if existing:
            events = list(
                (
                    await db.execute(
                        select(
                            MedicationEvent
                        )
                        .where(
                            MedicationEvent
                            .schedule_id
                            == existing.id
                        )
                        .order_by(
                            MedicationEvent
                            .scheduled_at
                        )
                    )
                ).scalars()
            )

            results.append(
                _schedule_dict(
                    existing,
                    med,
                    events,
                )
            )

            continue

        start = (
            med.start_date
            or datetime.now(
                _timezone(
                    settings
                    .DEFAULT_TIMEZONE
                )
            ).date()
        )

        end = (
            med.end_date
            or scheduler.parse_duration(
                med.duration,
                start,
            )
        )

        parsed = (
            scheduler.parse_frequency(
                med.frequency
            )
        )

        if (
            med.as_needed
            or parsed.get(
                "kind"
            )
            == "prn"
        ):
            # PRN medicines are shown as instructions
            # but intentionally have no fixed alarms.
            end = end or start

        elif end is None:
            continue

        events_dt, reason = (
            scheduler.build_events(
                med.frequency or "",
                start,
                end,
                settings.DEFAULT_TIMEZONE,
            )
        )

        if reason:
            continue

        instructions = "; ".join(
            x
            for x in [
                med.dose
                or med.strength,

                med.frequency,

                med.food_instruction,

                med.timing,

                med.duration,
            ]
            if x
        )

        schedule = (
            MedicationSchedule(
                consultation_id=
                    consultation.id,

                consultation_medication_id=
                    med.id,

                patient_id=
                    consultation.patient_id,

                timezone=
                    settings
                    .DEFAULT_TIMEZONE,

                instructions=
                    instructions,

                start_date=
                    start,

                end_date=
                    end,

                active=True,
            )
        )

        db.add(
            schedule
        )

        await db.flush()

        events = []

        for dt in events_dt:
            event = (
                MedicationEvent(
                    schedule_id=
                        schedule.id,

                    scheduled_at=
                        dt,

                    status=
                        "pending",

                    # Generated on demand and cached when
                    # voice assistance is enabled.
                    reminder_audio_path=
                        None,
                )
            )

            db.add(event)
            events.append(event)

        await db.flush()

        results.append(
            _schedule_dict(
                schedule,
                med,
                events,
            )
        )

    await audit(
        db,
        actor_id,
        "medication.schedules_generated",
        "consultation",
        consultation.id,
        {
            "count":
                len(results)
        },
    )

    return results


# ---------------------------------------------------------
# DOCTOR GENERATE
# ---------------------------------------------------------

@router.post(
    "/consultation/{cid}/generate"
)
async def generate(
    cid: int,
    db: AsyncSession =
        Depends(get_db),
    user: User =
        Depends(
            get_current_user
        ),
):
    consultation = (
        await db.execute(
            select(
                Consultation
            ).where(
                Consultation.id
                == cid
            )
        )
    ).scalar_one_or_none()

    if not consultation:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Consultation not found",
        )

    require_owner_doctor(
        user,
        consultation,
    )

    require_released(
        consultation
    )

    return (
        await generate_for_consultation(
            db,
            consultation,
            user.id,
        )
    )


# ---------------------------------------------------------
# CONSULTATION SCHEDULES
# ---------------------------------------------------------

@router.get(
    "/consultation/{cid}"
)
async def for_consultation(
    cid: int,
    db: AsyncSession =
        Depends(get_db),
    user: User =
        Depends(
            get_current_user
        ),
):
    consultation = (
        await db.execute(
            select(
                Consultation
            ).where(
                Consultation.id
                == cid
            )
        )
    ).scalar_one_or_none()

    if not consultation:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Consultation not found",
        )

    await require_can_view_consultation(
        db,
        user,
        consultation,
    )

    if (
        user.role
        == UserRole.PATIENT
    ):
        require_released(
            consultation
        )

    schedules = list(
        (
            await db.execute(
                select(
                    MedicationSchedule
                )
                .where(
                    MedicationSchedule
                    .consultation_id
                    == cid
                )
                .order_by(
                    MedicationSchedule.id
                )
            )
        ).scalars()
    )

    output = []

    for schedule in schedules:
        med = (
            await db.execute(
                select(
                    ConsultationMedication
                ).where(
                    ConsultationMedication
                    .id
                    == schedule
                    .consultation_medication_id
                )
            )
        ).scalar_one()

        events = list(
            (
                await db.execute(
                    select(
                        MedicationEvent
                    )
                    .where(
                        MedicationEvent
                        .schedule_id
                        == schedule.id
                    )
                    .order_by(
                        MedicationEvent
                        .scheduled_at
                    )
                )
            ).scalars()
        )

        output.append(
            _schedule_dict(
                schedule,
                med,
                events,
            )
        )

    return output


# ---------------------------------------------------------
# PATIENT ACTIVE SCHEDULES
# ---------------------------------------------------------

@router.get(
    "/mine"
)
async def mine(
    db: AsyncSession =
        Depends(get_db),
    patient: User =
        Depends(
            get_current_user
        ),
):
    if (
        patient.role
        != UserRole.PATIENT
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Patient access required",
        )

    schedules = list(
        (
            await db.execute(
                select(
                    MedicationSchedule
                )
                .where(
                    MedicationSchedule
                    .patient_id
                    == patient.id,

                    MedicationSchedule
                    .active
                    .is_(True),
                )
                .order_by(
                    MedicationSchedule.id
                )
            )
        ).scalars()
    )

    output = []

    for schedule in schedules:
        med = (
            await db.execute(
                select(
                    ConsultationMedication
                ).where(
                    ConsultationMedication
                    .id
                    == schedule
                    .consultation_medication_id
                )
            )
        ).scalar_one()

        events = list(
            (
                await db.execute(
                    select(
                        MedicationEvent
                    )
                    .where(
                        MedicationEvent
                        .schedule_id
                        == schedule.id
                    )
                    .order_by(
                        MedicationEvent
                        .scheduled_at
                    )
                )
            ).scalars()
        )

        output.append(
            _schedule_dict(
                schedule,
                med,
                events,
            )
        )

    return output


# ---------------------------------------------------------
# TAKEN / SNOOZE / SKIP
# ---------------------------------------------------------

@router.post(
    "/events/{event_id}/action"
)
async def event_action(
    event_id: int,
    body: EventAction,
    db: AsyncSession =
        Depends(get_db),
    patient: User =
        Depends(
            get_current_user
        ),
):
    if (
        patient.role
        != UserRole.PATIENT
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Patient access required",
        )

    event = (
        await db.execute(
            select(
                MedicationEvent
            ).where(
                MedicationEvent.id
                == event_id
            )
        )
    ).scalar_one_or_none()

    if not event:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Reminder not found",
        )

    schedule = (
        await db.execute(
            select(
                MedicationSchedule
            ).where(
                MedicationSchedule.id
                == event.schedule_id
            )
        )
    ).scalar_one()

    if (
        schedule.patient_id
        != patient.id
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Not your reminder",
        )

    timezone = (
        schedule.timezone
        or settings.DEFAULT_TIMEZONE
    )

    now = (
        datetime.now(
            _timezone(
                timezone
            )
        )
        .replace(
            tzinfo=None
        )
    )

    if (
        body.action
        == "snooze"
    ):
        event.status = (
            "snoozed"
        )

        event.snoozed_until = (
            now
            + timedelta(
                minutes=
                    body
                    .snooze_minutes
            )
        )

        # The spoken reminder contains the event time,
        # so regenerate it for the new snoozed time.
        event.reminder_audio_path = (
            None
        )

    else:
        event.status = (
            "taken"
            if body.action
            == "taken"
            else "skipped"
        )

        event.action_at = now

        event.snoozed_until = (
            None
        )

    await audit(
        db,
        patient.id,
        f"medication.{event.status}",
        "medication_event",
        event.id,
        {
            "scheduled_at":
                (
                    event
                    .scheduled_at
                    .isoformat()
                    if event
                    .scheduled_at
                    else None
                ),

            "snoozed_until":
                (
                    event
                    .snoozed_until
                    .isoformat()
                    if event
                    .snoozed_until
                    else None
                ),
        },
    )

    return {
        "id":
            event.id,

        "status":
            event.status,

        "snoozed_until":
            _aware_iso(
                event.snoozed_until,
                timezone,
            ),
    }


# ---------------------------------------------------------
# EVENT VOICE
# ---------------------------------------------------------


@router.get("/voice-test")
async def patient_voice_test(
    patient=Depends(get_current_user),
):
    role = getattr(
        getattr(
            patient,
            "role",
            None,
        ),
        "value",
        getattr(
            patient,
            "role",
            None,
        ),
    )

    if str(role).lower() != "patient":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Patient access required",
        )

    lang = (
        getattr(
            patient,
            "preferred_language",
            None,
        )
        or "en"
    )

    samples = {
        "ar":
            "هذا اختبار للتذكير الصوتي بالأدوية. "
            "الصوت يعمل بشكل صحيح.",

        "ps":
            "دا د درملو د غږیزې یادونې ازموینه ده. "
            "غږ په سمه توګه کار کوي.",

        "sd":
            "هي دوائن جي آواز واري ياد ڏيارڻي "
            "جي آزمائش آهي. آواز صحيح ڪم ڪري رهيو آهي.",
    }

    if lang not in samples:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            (
                "Independent voice test is "
                "enabled only for Arabic, "
                "Pashto and Sindhi."
            ),
        )

    try:
        audio = (
            await asyncio.to_thread(
                production_tts.synthesise,
                samples[lang],
                lang,
                None,
            )
        )

    except Exception as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            (
                "Voice test generation failed: "
                f"{exc}"
            ),
        )

    if not audio:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Voice test generated no audio",
        )

    audio_path = str(audio)

    media = (
        mimetypes.guess_type(
            audio_path
        )[0]
        or "audio/wav"
    )

    return FileResponse(
        audio_path,
        media_type=media,
        filename=audio_path
        .rsplit("/", 1)[-1],
    )


@router.get(
    "/events/{event_id}/audio"
)
async def event_audio(
    event_id: int,
    db: AsyncSession =
        Depends(get_db),
    patient: User =
        Depends(
            get_current_user
        ),
):
    if (
        patient.role
        != UserRole.PATIENT
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Patient access required",
        )

    event = (
        await db.execute(
            select(
                MedicationEvent
            ).where(
                MedicationEvent.id
                == event_id
            )
        )
    ).scalar_one_or_none()

    if not event:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Reminder not found",
        )

    schedule = (
        await db.execute(
            select(
                MedicationSchedule
            ).where(
                MedicationSchedule.id
                == event.schedule_id
            )
        )
    ).scalar_one()

    if (
        schedule.patient_id
        != patient.id
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Not your reminder",
        )

    med = (
        await db.execute(
            select(
                ConsultationMedication
            ).where(
                ConsultationMedication.id
                == schedule
                .consultation_medication_id
            )
        )
    ).scalar_one()

    consultation = (
        await db.execute(
            select(
                Consultation
            ).where(
                Consultation.id
                == schedule
                .consultation_id
            )
        )
    ).scalar_one()

    try:
        path = (
            await _ensure_event_audio(
                db,
                consultation,
                schedule,
                med,
                event,
            )
        )

    except Exception as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            (
                "Reminder voice could not "
                f"be generated: {exc}"
            ),
        )

    if (
        not path
        or not path.exists()
    ):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Reminder audio unavailable",
        )

    media = (
        mimetypes
        .guess_type(
            path.name
        )[0]
        or "audio/wav"
    )

    return FileResponse(
        path,
        media_type=media,
        filename=path.name,
    )
