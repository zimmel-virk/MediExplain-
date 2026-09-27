"""Grounded clinical text generation through local Ollama.

Clinical note and patient explanation are generated independently so SOAP text
cannot leak into the patient output. The raw transcript is never silently
rewritten before summarisation.
"""
from __future__ import annotations
import json, logging
from typing import Any
import httpx
from app.core.config import settings
from app.schemas import StructuredData

logger=logging.getLogger(__name__)


# These grounding rules are shared across the clinical LLM tasks in this file.
# They keep the local Ollama model tied to information actually present in the
# consultation transcript and place stricter controls around medication names,
# doses, frequencies, durations, negation and uncertainty. The model is also
# reminded that its output remains a draft until it has been reviewed by the
# treating doctor.

GROUND_RULES = """You are an assistive medical scribe in an academic research prototype.

Use ONLY facts explicitly present in the source transcript.

Do not independently diagnose, prescribe, infer tests, add warning signs,
invent people, invent relationships, invent causes, or invent doses.

MEDICATION SAFETY RULES:
- Preserve medication names exactly as supported by the source.
- Preserve dose/strength exactly.
- Preserve frequency and duration as TWO SEPARATE concepts.
- Never convert frequency into duration.
- Never convert duration into frequency.
- "twice daily for 2 days" means TWO TIMES EACH DAY, for a TOTAL DURATION
  of TWO DAYS.
- "twice daily for 2 days" must NEVER become "every 2 days".
- "three times daily for 5 days" must NEVER become "every 5 days".
- "every 8 hours for 3 days" must retain BOTH the 8-hour frequency and
  the 3-day duration.
- Preserve timing such as morning, night, before food and after food
  separately from frequency and duration.
- Do not invent who gave or recommended a medicine.
- If the transcript does not identify a person, never add one.
- If medication wording is unclear, preserve the uncertainty rather than
  guessing.

Preserve medication names, quantities, units, frequencies, timing,
durations, negations and dates exactly.

If information is absent, say it was not mentioned.

The treating doctor must review everything before patient release."""


# This prompt is used when the LLM converts the consultation transcript into
# structured clinical data. It forces the model to return the expected JSON
# fields and keeps medication strength, frequency, timing and duration separate
# so these details can later be validated and reviewed individually.
STRUCTURE_SYSTEM=GROUND_RULES+"""
Return ONLY JSON matching:
{
 "chief_complaint": string|null,
 "symptoms": [string],
 "relevant_history": [string],
 "diagnosis_discussed": [string],
 "diagnosis_status": "confirmed"|"suspected"|"discussed"|null,
 "medications": [{
   "name": string, "name_as_heard": string, "confidence": number,
   "dose": string|null, "strength": string|null, "dose_unit": string|null,
   "dosage_form": string|null, "route": string|null, "frequency": string|null,
   "timing": string|null, "food_instruction": string|null, "duration": string|null,
   "as_needed": boolean, "indication": string|null, "notes": string|null,
   "doctor_confirmed": false, "suggestions": []
 }],
 "tests": [string], "advice": [string],
 "follow_up": string|null, "warning_signs": [string],
 "glossary": [{"term":string,"plain_explanation":string}]
}
Do not turn timing such as 'after food' into duration. Do not convert a brand
to a generic name unless the transcript itself said both; preserve the heard
name and let the medication terminology service verify identity."""


# This extra instruction gives the LLM a concrete medication example so that
# frequency and duration are not accidentally merged during structured extraction.
STRUCTURE_SYSTEM += """
Medication field separation is safety-critical.

Example:
"500 mg twice daily for 2 days after food"

must be extracted as:
{
  "strength": "500 mg",
  "frequency": "twice daily",
  "duration": "2 days",
  "food_instruction": "after food"
}

Never produce:
{
  "frequency": "every 2 days"
}

from that instruction.
"""

# This prompt tells the LLM to create the doctor-facing clinical draft in SOAP
# format. The note must remain grounded in the transcript and must preserve
# uncertainty instead of turning a suspected or discussed diagnosis into a
# confirmed one.

CLINICAL_SYSTEM=GROUND_RULES+"""
Write a concise doctor-facing SOAP draft with exactly four headings:
Subjective, Objective, Assessment, Plan.
If a section has no source evidence, write 'Not mentioned in transcript.'
Clearly retain wording such as 'doctor suspects' rather than upgrading it to a
confirmed diagnosis. Do not add standard-of-care advice that was not spoken."""


# This prompt controls the separate patient-facing LLM output. The model is asked
# to explain only what was discussed during the consultation using simpler
# language while keeping medication instructions and other clinical details exact.
# It is generated independently from the SOAP note so clinician-style wording does
# not automatically flow into the patient explanation.
PATIENT_SYSTEM = GROUND_RULES + """
Write only a plain-English patient explanation.

No SOAP headings, markdown prompt delimiters, or clinical-note language.

Target approximately Grade 6:
short sentences, common words, and brief explanations of unavoidable terms.

Cover only what was actually discussed:
- problem/symptoms
- doctor-stated assessment if any
- instructions
- medicines
- follow-up
- warning signs

Medication instructions must remain unambiguous.

For every medicine:
- medicine name is one field
- dose/strength is one field
- frequency is one field
- timing is one field
- duration is one field

Example:
"Paracetamol 500 mg twice daily for 2 days after food"

means:
Medicine: Paracetamol
Strength: 500 mg
Frequency: twice daily
Duration: 2 days
Food instruction: after food

It DOES NOT mean:
"take every 2 days"

Do not append generic emergency advice unless the transcript explicitly
said it.

Do not introduce a new diagnosis, treatment, person, relative, cause,
frequency or duration."""


# These rules keep the structured and clinician-facing LLM outputs in English
# while preserving clinically important numbers, medication details, negation
# and uncertainty from the source consultation.
ENGLISH_CLINICAL_RULES = """
IMPORTANT OUTPUT LANGUAGE RULES:
- All clinician-facing output must be in English.
- All structured JSON textual values must be English.
- Medication names should use their standard English/Latin spelling where possible.
- Dose, frequency, timing and duration must be expressed in English.
- Preserve exact numbers, medicine names, negation and uncertainty.
- Do not introduce any information absent from the source transcript.
"""

# This prompt is used when the LLM needs to translate a multilingual or
# code-switched consultation transcript into English before later clinical
# processing. It requests a faithful translation rather than a summary and
# prevents the model from adding new diagnosis, treatment or advice

ENGLISH_TRANSCRIPT_SYSTEM = """
You are a medical transcript translator.

Translate the supplied consultation transcript faithfully into English.

Rules:
- This is a translation, NOT a summary.
- Preserve every clinically meaningful statement.
- Preserve medication names.
- Preserve exact numbers, doses, frequency and duration.
- Preserve negation.
- Preserve uncertainty.
- Preserve whether a statement came from the doctor or patient when labels exist.
- English phrases already present in code-switched speech should remain English.
- Do not add diagnoses, advice or treatment.
- Return ONLY the faithful English transcript.
"""

# This prompt gives the LLM a much narrower role when reviewing speech-to-text
# output. It can suggest obvious ASR or spelling corrections, but it returns
# suggestions separately instead of rewriting the original clinical transcript.
CORRECTION_SYSTEM="""You are reviewing speech recognition output only.
Return a JSON array of suggested corrections, never a rewritten source.
Each object must have {"original": "...", "suggested": "...", "reason": "..."}.
Suggest only obvious spelling/ASR corrections. Do not infer new clinical facts."""


# This is the shared connection to the local Ollama LLM. It sends the selected
# system instructions and task prompt to the model configured in the application
# settings. A low temperature is used to keep clinical generation more
# deterministic, and JSON mode can be enabled for tasks that require structured
# output rather than free text.
async def _call_ollama(system:str,user:str,json_mode:bool=False)->str:
    payload={
        "model":settings.OLLAMA_MODEL,"prompt":user,"system":system,"stream":False,
        "options":{"temperature":0.1,"num_ctx":settings.OLLAMA_NUM_CTX},
    }
    if json_mode: payload["format"]="json"
    async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
        r=await client.post(f"{settings.OLLAMA_HOST}/api/generate",json=payload)
        r.raise_for_status()
        return r.json().get("response","")


# This function asks the LLM to extract structured clinical information directly
# from the transcript, including symptoms, discussed diagnoses, medications,
# tests, advice and follow-up information. The returned JSON is then passed
# through the StructuredData schema so malformed model output does not continue
# through the workflow as valid structured clinical data.
async def extract_structured_data(
    transcript: str,
) -> dict:
    if (
        not transcript
        or len(
            transcript.strip()
        ) < 10
    ):
        return (
            StructuredData()
            .model_dump()
        )

    raw = await _call_ollama(
        STRUCTURE_SYSTEM
        + ENGLISH_CLINICAL_RULES,
        (
            "SOURCE TRANSCRIPT:\n"
            f"{transcript}"
        ),
        True,
    )

    try:
        return StructuredData(
            **json.loads(raw)
        ).model_dump()

    except Exception as exc:
        logger.error(
            "Structured extraction "
            "parse failure: %s",
            exc,
        )

        return (
            StructuredData()
            .model_dump()
        )

# This function uses the local LLM to create the doctor-facing SOAP draft.
# The original transcript remains the main source, while the structured
# extraction can be supplied as additional grounded context. The model is still
# instructed not to introduce clinical information that was not present in the
# consultation.
async def generate_clinical_note(
    transcript: str,
    structured: dict | None = None,
) -> str:
    if not transcript.strip():
        return (
            "Not enough transcript to "
            "create a clinical draft."
        )

    context = (
        "SOURCE TRANSCRIPT:\n"
        f"{transcript}\n"
    )

    if structured:
        context += (
            "\nSTRUCTURED EXTRACTION "
            "(must still be grounded):\n"
            + json.dumps(
                structured,
                ensure_ascii=False,
            )
        )

    return (
        await _call_ollama(
            CLINICAL_SYSTEM
            + ENGLISH_CLINICAL_RULES,
            context,
        )
    ).strip()


# This function generates a separate plain-English explanation for the patient
# using the local LLM. It receives the transcript and, when available, the
# structured extraction, but uses its own patient-specific prompt rather than
# generating the explanation from the doctor's SOAP note.
async def generate_patient_summary(
    transcript: str,
    structured: dict | None = None,
) -> str:
    if not transcript.strip():
        return (
            "There was not enough "
            "recorded speech to create "
            "an explanation."
        )

    context = (
        "SOURCE TRANSCRIPT:\n"
        f"{transcript}\n"
    )

    if structured:
        context += (
            "\nSTRUCTURED EXTRACTION:\n"
            + json.dumps(
                structured,
                ensure_ascii=False,
            )
        )

    return (
        await _call_ollama(
            PATIENT_SYSTEM
            + ENGLISH_CLINICAL_RULES,
            context,
        )
    ).strip()

# This function uses the LLM to translate a multilingual or code-switched
# consultation transcript into English. Detected languages are included as
# context, while the prompt requires the model to preserve clinically important
# statements, medication details, numbers, negation and uncertainty.
async def translate_transcript_to_english(
    transcript: str,
    languages: list[str] | None = None,
) -> str:
    if not transcript.strip():
        return ""

    language_note = (
        ", ".join(
            languages or []
        )
        or "auto-detected multilingual speech"
    )

    prompt = (
        f"DETECTED LANGUAGES: {language_note}\n\n"
        "SOURCE CONSULTATION TRANSCRIPT:\n"
        f"{transcript}"
    )

    translated = await _call_ollama(
        ENGLISH_TRANSCRIPT_SYSTEM,
        prompt,
    )

    return translated.strip()

# This function brings the three main LLM stages together for an English
# consultation. It first extracts structured information, then uses that
# grounded data alongside the transcript to create the doctor-facing clinical
# note and the separate patient-facing explanation.
async def summarise_consultation(transcript:str)->dict[str,str]:
    structured=await extract_structured_data(transcript)
    clinical=await generate_clinical_note(transcript,structured)
    patient=await generate_patient_summary(transcript,structured)
    return {"clinical_note":clinical,"patient_summary":patient}


# This function asks the LLM to identify likely speech-recognition mistakes
# without modifying the stored transcript itself. Suggestions are returned as
# structured original/suggested/reason entries so a human can review the proposed
# correction rather than accepting an automatic rewrite of the clinical source.
async def suggest_transcript_corrections(transcript:str)->list[dict]:
    if not transcript or len(transcript)<20: return []
    try:
        raw=await _call_ollama(CORRECTION_SYSTEM,f"RAW STT:\n{transcript}",True)
        data=json.loads(raw)
        if isinstance(data,dict): data=data.get("corrections",[])
        return data if isinstance(data,list) else []
    except Exception as exc:
        logger.warning("Correction suggestions unavailable: %s",exc)
        return []


# This function keeps the older normalisation interface available for parts of
# the application that still call it. It deliberately returns the transcript
# unchanged so code-switched clinical speech is not silently rewritten before
# summarisation or review.
async def normalise_codeswitched_transcript(transcript:str)->str:
    return transcript
