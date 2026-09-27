"""Patient-facing PDF export for released MediExplain+ summaries.

This renderer is additive to the original project. It uses the original released
summary/medication/schedule data, adds the reminder timetable to the PDF, and
renders Arabic-derived scripts with reshaping/BiDi when the optional PDF
language dependencies are installed.
"""
from __future__ import annotations

import logging
from datetime import datetime
from html import escape
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Consultation, ConsultationMedication, MedicationEvent, MedicationSchedule, User

# This file creates the downloadable patient PDF after a MediExplain+ consultation
# has been released. It reads the final patient summary together with the doctor's
# confirmed medication records and the existing medication reminder schedules,
# then formats them into a clear patient-facing document. The renderer supports
# multilingual labels, right-to-left scripts such as Urdu, Arabic, Pashto, Sindhi
# and Shahmukhi Punjabi, selects an available Unicode font, and includes follow-up
# information, warning signs, glossary terms and upcoming reminder times where
# they are available. The PDF is built from the released consultation data rather
# than generating new clinical information during export.

logger = logging.getLogger(__name__)

RTL_LANGS = {"ur", "pa_shah", "ar", "ps", "sd"}

PDF_TEXT = {
    "en": {
        "title": "Patient Consultation Summary", "released": "Released patient information",
        "summary": "Written summary", "meds": "Medication instructions", "dose": "Dose / strength",
        "form": "Amount / form", "frequency": "Frequency", "timing": "Timing", "duration": "Duration",
        "notes": "Instructions / notes", "schedule": "Medication schedule", "next": "Upcoming reminder times",
        "follow": "Follow-up", "warnings": "Warning signs discussed", "glossary": "Plain-language glossary",
        "none": "No doctor-confirmed medications were recorded for this consultation.",
        "no_schedule": "No medication reminder schedule has been generated.",
        "disclaimer": "Doctor-released consultation explanation; not an independent diagnosis or prescription.",
    },
    "ur": {
        "title": "مریض کی مشاورت کا خلاصہ", "released": "مریض کے لیے جاری کی گئی معلومات",
        "summary": "تحریری خلاصہ", "meds": "ادویات کی ہدایات", "dose": "خوراک / طاقت",
        "form": "مقدار / شکل", "frequency": "کتنی بار", "timing": "کب لینی ہے", "duration": "مدت",
        "notes": "ہدایات / نوٹس", "schedule": "ادویات کا شیڈول", "next": "آنے والی یاددہانی کے اوقات",
        "follow": "فالو اَپ", "warnings": "بتائی گئی احتیاطی علامات", "glossary": "سادہ الفاظ میں طبی اصطلاحات",
        "none": "اس مشاورت میں ڈاکٹر کی تصدیق شدہ کوئی دوا درج نہیں کی گئی۔",
        "no_schedule": "ادویات کے لیے یاددہانی کا شیڈول ابھی نہیں بنایا گیا۔",
        "disclaimer": "یہ ڈاکٹر کی طرف سے جاری کردہ مشاورت کی وضاحت ہے؛ یہ خودکار تشخیص یا نسخہ نہیں ہے۔",
    },
    "pa_shah": {
        "title": "مریض دی کنسلٹیشن دا خلاصہ", "released": "مریض لئی جاری کیتی معلومات",
        "summary": "لکھیا ہویا خلاصہ", "meds": "دوائیاں دیاں ہدایتاں", "dose": "خوراک / طاقت",
        "form": "مقدار / شکل", "frequency": "کِنّی واری", "timing": "کدوں لینی اے", "duration": "مدت",
        "notes": "ہدایتاں / نوٹس", "schedule": "دوائی دا شیڈول", "next": "اگلی یاددہانیاں دے ویلے",
        "follow": "فالو اَپ", "warnings": "دسیاں گئیاں خبردار کرن والیاں نشانیاں", "glossary": "سادے لفظاں وچ طبی اصطلاحاں",
        "none": "ایس کنسلٹیشن وچ ڈاکٹر ولوں تصدیق کیتی کوئی دوائی درج نئیں۔",
        "no_schedule": "دوائی دا یاددہانی شیڈول ہن تک نئیں بنایا گیا۔",
        "disclaimer": "ایہ ڈاکٹر ولوں جاری کیتی کنسلٹیشن دی وضاحت اے؛ ایہ خودکار تشخیص یا نسخہ نئیں۔",
    },
}


def _labels(lang: str) -> dict:
    return PDF_TEXT.get(lang, PDF_TEXT["en"])


def _font_candidates() -> list[tuple[str, str | None]]:
    return [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf", None),
        ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", None),
        ("/Library/Fonts/Arial Unicode.ttf", None),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ("/System/Library/Fonts/Supplemental/Times New Roman.ttf", "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"),
    ]


def _safe(value) -> str:
    return escape("" if value is None else str(value), quote=False)


async def medication_payload(db: AsyncSession, consultation_id: int) -> list[dict]:
    """Return the doctor-confirmed medication rows from the original medication table.

    This deliberately reads the initial project's canonical consultation_medications
    records so PDF delivery reflects the doctor's edits rather than a stale LLM JSON
    snapshot.
    """
    rows = list((await db.execute(
        select(ConsultationMedication).where(
            ConsultationMedication.consultation_id == consultation_id,
            ConsultationMedication.doctor_confirmed.is_(True),
        ).order_by(ConsultationMedication.id)
    )).scalars())
    return [
        {
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
            "indication": m.indication,
            "notes": m.notes,
            "doctor_confirmed": bool(m.doctor_confirmed),
        }
        for m in rows
    ]


async def schedule_payload(db: AsyncSession, consultation_id: int) -> list[dict]:
    """Return the existing original scheduler's persisted timetable for the PDF."""
    schedules = list((await db.execute(
        select(MedicationSchedule).where(
            MedicationSchedule.consultation_id == consultation_id,
            MedicationSchedule.active.is_(True),
        ).order_by(MedicationSchedule.id)
    )).scalars())

    output: list[dict] = []
    for schedule in schedules:
        med = (await db.execute(select(ConsultationMedication).where(
            ConsultationMedication.id == schedule.consultation_medication_id
        ))).scalar_one_or_none()
        if not med:
            continue
        events = list((await db.execute(select(MedicationEvent).where(
            MedicationEvent.schedule_id == schedule.id,
        ).order_by(MedicationEvent.scheduled_at))).scalars())
        output.append({
            "medication_name": med.canonical_name or med.raw_name or "Medication",
            "dose": med.dose or med.strength,
            "strength": med.strength,
            "dosage_form": med.dosage_form,
            "frequency": med.frequency,
            "timing": med.timing,
            "food_instruction": med.food_instruction,
            "duration": med.duration,
            "instructions": schedule.instructions,
            "timezone": schedule.timezone or settings.DEFAULT_TIMEZONE,
            "events": [
                {
                    "scheduled_at": e.scheduled_at.isoformat() if e.scheduled_at else None,
                    "status": e.status,
                    "snoozed_until": e.snoozed_until.isoformat() if e.snoozed_until else None,
                }
                for e in events
            ],
        })
    return output


def generate_patient_pdf(
    consultation: Consultation,
    patient: User,
    doctor: User,
    output_path: Path,
    schedules: list[dict] | None = None,
    medications: list[dict] | None = None,
) -> Path:
    """Render the released patient summary and original deterministic schedule."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError(f"PDF language support is not installed: {exc}") from exc

    lang = consultation.patient_language or "en"
    rtl = lang in RTL_LANGS
    labels = _labels(lang)

    font_name = "Helvetica"
    bold_name = "Helvetica-Bold"
    for regular, bold in _font_candidates():
        if not Path(regular).exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("MediUnicode", regular))
            font_name = "MediUnicode"
            if bold and Path(bold).exists():
                pdfmetrics.registerFont(TTFont("MediUnicodeBold", bold))
                bold_name = "MediUnicodeBold"
            else:
                bold_name = font_name
            break
        except Exception as exc:
            logger.warning("PDF font registration failed for %s: %s", regular, exc)

    def visual(text: str) -> str:
        text = str(text or "")
        if not rtl:
            return text
        try:
            return get_display(arabic_reshaper.reshape(text))
        except Exception:
            return text

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4
    left, right = 48, 48
    y = height - 54
    line_height = 16

    def new_page():
        nonlocal y
        pdf.showPage()
        y = height - 54

    def draw_line(text: str, font=font_name, size=10, indent=0, force_rtl: bool | None = None):
        nonlocal y
        if y < 65:
            new_page()
        pdf.setFont(font, size)
        use_rtl = rtl if force_rtl is None else force_rtl
        shown = visual(text) if use_rtl else str(text or "")
        if use_rtl:
            pdf.drawRightString(width - right - indent, y, shown)
        else:
            pdf.drawString(left + indent, y, shown)
        y -= line_height

    def wrapped(text: str, indent=0, size=10, force_rtl: bool | None = None):
        nonlocal y
        text = str(text or "").strip()
        if not text:
            return
        use_rtl = rtl if force_rtl is None else force_rtl
        max_width = width - left - right - indent
        for para in text.splitlines() or [text]:
            words = para.split()
            if not words:
                y -= line_height
                continue
            line = ""
            for word in words:
                test = (line + " " + word).strip()
                shown = visual(test) if use_rtl else test
                pdf.setFont(font_name, size)
                if pdf.stringWidth(shown, font_name, size) > max_width and line:
                    draw_line(line, font_name, size, indent, use_rtl)
                    line = word
                else:
                    line = test
            if line:
                draw_line(line, font_name, size, indent, use_rtl)
            y -= 2

    def heading(text: str, size=14):
        nonlocal y
        if y < 90:
            new_page()
        draw_line(text, bold_name, size)
        y -= 3

    pdf.setTitle("MediExplain+ Patient Summary")
    pdf.setFont(bold_name, 18)
    pdf.drawString(left, y, "MediExplain+")
    y -= 25
    heading(labels["title"], 16)
    meta = f"{labels['released']} · #{consultation.id}"
    wrapped(meta, size=9)
    wrapped(f"{patient.full_name} · {doctor.full_name} · {consultation.created_at.strftime('%d %B %Y')}", size=9, force_rtl=False)
    y -= 8

    summary = consultation.patient_summary_translated or consultation.doctor_edited_summary or consultation.patient_summary_en or "—"
    heading(labels["summary"])
    wrapped(summary)

    if medications is None:
        # Backward-compatible fallback for an older exported consultation where
        # only the structured JSON is available. Normal authenticated/shared PDF
        # routes pass the canonical doctor-confirmed table rows above.
        meds = [
            m for m in ((consultation.structured_data or {}).get("medications", []) or [])
            if bool(m.get("doctor_confirmed"))
        ]
    else:
        meds = medications
    heading(labels["meds"])
    if not meds:
        wrapped(labels["none"])
    for idx, med in enumerate(meds, 1):
        name = med.get("canonical_name") or med.get("brand_name") or med.get("generic_name") or med.get("raw_name") or med.get("name") or med.get("name_as_heard") or "Medication"
        dose = med.get("dose") or med.get("strength") or ""
        form = med.get("dosage_form") or ""
        draw_line(f"{idx}. {name}", bold_name, 10, force_rtl=False if name and name[:1].isascii() else None)
        pairs = [
            (labels["dose"], dose), (labels["form"], form),
            (labels["frequency"], med.get("frequency")),
            (labels["timing"], "; ".join(x for x in [med.get("timing"), med.get("food_instruction")] if x)),
            (labels["duration"], med.get("duration")),
            (labels["notes"], med.get("notes")),
        ]
        for label, value in pairs:
            if value:
                wrapped(f"{label}: {value}", indent=14, size=9)
        y -= 3

    heading(labels["schedule"])
    schedules = schedules or []
    if not schedules:
        wrapped(labels["no_schedule"])
    for sched in schedules:
        med_title = " ".join(x for x in [sched.get("medication_name"), sched.get("dose"), sched.get("dosage_form")] if x)
        draw_line(med_title or "Medication", bold_name, 10, force_rtl=False if med_title and med_title[:1].isascii() else None)
        detail = " · ".join(x for x in [sched.get("frequency"), sched.get("timing"), sched.get("food_instruction"), sched.get("duration")] if x)
        if detail:
            wrapped(detail, indent=14, size=9)
        pending = [e for e in (sched.get("events") or []) if e.get("status") == "pending"]
        if pending:
            wrapped(labels["next"] + ":", indent=14, size=9)
            for event in pending:
                raw = event.get("snoozed_until") or event.get("scheduled_at")
                try:
                    dt = datetime.fromisoformat(raw) if raw else None
                    when = dt.strftime("%d %b %Y · %I:%M %p") if dt else ""
                except Exception:
                    when = raw or ""
                wrapped(f"• {when}", indent=28, size=9, force_rtl=False)
        y -= 3

    structured = consultation.structured_data or {}
    follow = structured.get("follow_up")
    if follow:
        heading(labels["follow"])
        wrapped(follow)
    warnings = structured.get("warning_signs", []) or []
    if warnings:
        heading(labels["warnings"])
        for item in warnings:
            wrapped(f"• {item}")
    glossary = structured.get("glossary", []) or []
    if glossary:
        heading(labels["glossary"])
        for item in glossary:
            wrapped(f"{item.get('term', '')}: {item.get('plain_explanation', '')}")

    y -= 8
    wrapped(labels["disclaimer"], size=8)
    pdf.save()
    return output_path
