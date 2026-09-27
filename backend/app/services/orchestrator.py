"""Integrated AI orchestration pipeline for MediExplain+ Final."""
from __future__ import annotations
import asyncio,logging,time
from pathlib import Path
from app.core.config import settings
from app.services import llm,nli,stt,translation,tts
from app.services import medication_index

logger=logging.getLogger(__name__)

# This is the main AI orchestration function for a MediExplain+ consultation.
# It coordinates the complete processing pipeline from speech transcription through
# structured clinical extraction, medication matching, separate doctor and patient
# summaries, grounding checks, multilingual translation and patient-facing speech.
# Each model stage keeps its own metadata and failures so one component can be
# reviewed independently instead of hiding errors inside a single AI response.
async def process_consultation(
    audio_path: str | Path | None,
    patient_language: str = "en",
    primary_language: str | None = None,
    secondary_language: str | None = None,
    transcript_override: str | None = None,
    transcript_segments_override: list[dict] | None = None,
) -> dict:
    started=time.perf_counter()
    result={
        "transcript":None,"transcript_raw":None,"transcript_segments":[],
        "transcript_correction_suggestions":[],
        "languages_detected":[],"code_switched":False,
        "clinical_note":None,"patient_summary_en":None,
        "patient_summary_translated":None,"structured_data":None,
        "safety_checks":[],"audio_summary_path":None,"tts_backend":None,
        "translation_quality":None,"translation_metadata":None,
        "dose_sentences_for_review":[],"errors":[],"model_metadata":{},
        "doctor_transcript_en": None,
    }

# The pipeline can start from either new consultation audio or a transcript that
# has already been reviewed by the doctor. New audio is transcribed by Whisper,
# while a supplied verified transcript is reused directly so doctor corrections
# are not overwritten by running speech recognition again.

    if transcript_override and transcript_override.strip():
        reviewed = transcript_override.strip()

        result["transcript_raw"] = reviewed
        result["transcript"] = reviewed

        result["transcript_segments"] = (
            transcript_segments_override
            or [
                {
                    "start": 0.0,
                    "end": 0.0,
                    "text": reviewed,
                    "language": primary_language,
                    "needs_review": False,
                }
            ]
        )

        languages = {
            s.get("language")
            for s in result["transcript_segments"]
            if s.get("language")
        }

        result["languages_detected"] = sorted(languages)
        result["code_switched"] = len(languages) > 1

        result["model_metadata"]["stt"] = {
            "source": "doctor_reviewed_transcript",
            "whisper_rerun": False,
        }

        # Retain warnings for any speech segments the doctor
        # has still not reviewed.
        for s in result["transcript_segments"]:
            if s.get("needs_review"):
                result["safety_checks"].append(
                    {
                        "check_type": "stt_confidence",
                        "status": "warning",
                        "severity": "high",
                        "statement": s.get("text"),
                        "evidence": (
                            f"{s.get('start', 0):.1f}-"
                            f"{s.get('end', 0):.1f}s"
                        ),
                        "score": s.get("confidence"),
                        "details": {
                            "source":
                                "reviewed_transcript",
                        },
                    }
                )

    else:
        try:
            t = time.perf_counter()

            sr = await asyncio.to_thread(
                stt.transcribe,
                audio_path,
                primary_language,
                secondary_language,
            )

            result["transcript_raw"] = sr["text"]
            result["transcript"] = sr["text"]
            result["transcript_segments"] = (
                sr.get("segments", [])
            )
            result["languages_detected"] = (
                sr.get("languages_detected", [])
            )
            result["code_switched"] = sr.get(
                "code_switched",
                False,
            )
            result["audio_duration"] = sr.get(
                "duration"
            )

            result["model_metadata"]["stt"] = {
                "model": settings.WHISPER_MODEL,
                "seconds": round(
                    time.perf_counter() - t,
                    3,
                ),
                "diarization": sr.get(
                    "diarization_available",
                    False,
                ),
            }

            for s in result["transcript_segments"]:
                if s.get("needs_review"):
                    result["safety_checks"].append(
                        {
                            "check_type":
                                "stt_confidence",
                            "status": "warning",
                            "severity": "high",
                            "statement": s.get("text"),
                            "evidence": (
                                f"{s.get('start', 0):.1f}-"
                                f"{s.get('end', 0):.1f}s"
                            ),
                            "score": s.get(
                                "confidence"
                            ),
                            "details": {
                                "avg_logprob":
                                    s.get(
                                        "avg_logprob"
                                    ),
                                "no_speech_prob":
                                    s.get(
                                        "no_speech_prob"
                                    ),
                            },
                        }
                    )

        except Exception as exc:
            logger.exception("STT failed")

            result["errors"].append(
                {
                    "stage": "stt",
                    "error": str(exc),
                }
            )

            return result


# For code-switched speech, the local LLM can suggest likely ASR corrections.
# These remain suggestions only and do not silently replace the stored transcript.

    if result["code_switched"]:
        result["transcript_correction_suggestions"]=await llm.suggest_transcript_corrections(result["transcript_raw"])

# The local clinical LLM first converts the transcript into structured information
# such as symptoms, history, discussed diagnoses, medications, tests and follow-up.
# Running this before summary generation gives the later stages a consistent clinical
# structure while the original transcript remains the grounding source.
    try:
        t=time.perf_counter()
        structured=await llm.extract_structured_data(result["transcript_raw"])
        result["structured_data"]=structured
        result["model_metadata"]["clinical_llm"]={
            "model":settings.OLLAMA_MODEL,
            "structured_seconds":round(time.perf_counter()-t,3),
        }
    except Exception as exc:
        result["errors"].append({"stage":"structured_extraction","error":str(exc)})
        return result

# Medication names extracted by the LLM are checked against the local authoritative
# terminology index. Candidate matches and confidence scores are attached for doctor
# review, but the pipeline deliberately leaves every medication unconfirmed until
# the doctor verifies its identity and instructions.
    try:
        medstats=medication_index.stats()
        meds=(result["structured_data"] or {}).get("medications",[]) or []
        for med in meds:
            q=(med.get("name_as_heard") or med.get("name") or "").strip()
            candidates=medication_index.suggest(q,top_k=settings.MEDICATION_MAX_RESULTS) if medstats["concepts"] else []
            med["suggestions"]=candidates
            med["match_confidence"]=candidates[0]["score"] if candidates else 0.0
            med["doctor_confirmed"]=False
            if not candidates:
                # Missing or weak terminology matches become high-priority review warnings rather
# than being accepted as valid medication identities.
                result["safety_checks"].append({
                    "check_type":"medication_match","status":"warning","severity":"high",
                    "statement":q or "Unclear medication","evidence":"Transcript extraction",
                    "score":0.0,
                    "details":{"reason":"No confident medication terminology match" if medstats["concepts"] else "Medication dataset not installed"}
                })
            elif candidates[0]["score"]<settings.MEDICATION_AUTO_ACCEPT_SCORE:
                result["safety_checks"].append({
                    "check_type":"medication_match","status":"warning","severity":"high",
                    "statement":q,"evidence":candidates[0]["display_name"],
                    "score":candidates[0]["score"],"details":{"candidates":candidates[:5]}
                })
    except Exception as exc:
        logger.warning("Medication index unavailable: %s",exc)
        result["errors"].append({"stage":"medication_match","error":str(exc)})
# The local LLM now creates two separate outputs in parallel: a doctor-facing
# clinical SOAP draft and a simpler patient-facing explanation. Both use the
# transcript and structured extraction, but the patient explanation is not derived
# from the SOAP note, which helps prevent clinician-only wording from leaking into
# the patient output.
    try:
        t=time.perf_counter()
        clinical_task=llm.generate_clinical_note(result["transcript_raw"],result["structured_data"])
        patient_task=llm.generate_patient_summary(result["transcript_raw"],result["structured_data"])
        clinical,patient=await asyncio.gather(clinical_task,patient_task)
        result["clinical_note"]=clinical
        result["patient_summary_en"]=patient
        result["model_metadata"].setdefault("clinical_llm",{})["summary_seconds"]=round(time.perf_counter()-t,3)
    except Exception as exc:
        logger.exception("Summary generation failed")
        result["errors"].append({"stage":"summary","error":str(exc)})
        return result
# DeBERTa-v3 NLI independently checks the generated patient explanation against
# the consultation transcript. Claims supported by transcript evidence pass,
# while contradictory or unsupported claims become unresolved safety warnings
# that require review before approval.
    try:
        t=time.perf_counter()
        seg_text=[s.get("text","") for s in result["transcript_segments"]]
        grounded=await asyncio.to_thread(nli.ground_summary,result["transcript_raw"],result["patient_summary_en"],seg_text)
        for g in grounded:
            # Each generated claim is converted into a stored safety-check result together
# with its strongest transcript evidence and entailment score.
            if g.get("label")=="entailed":
                status="pass";severity="low";resolved=True
            elif g.get("label")=="unavailable":
                status="unavailable";severity="low";resolved=True
            else:
                status="warning";severity="high";resolved=False
            result["safety_checks"].append({
                "check_type":"nli_grounding","status":status,"severity":severity,
                "statement":g.get("statement"),"evidence":g.get("evidence"),
                "score":g.get("entailment"),"details":g,"resolved":resolved,
            })
        result["model_metadata"]["nli"]={
            "model":settings.NLI_MODEL,
            "seconds":round(time.perf_counter()-t,3),
        }
    except Exception as exc:
        result["errors"].append({"stage":"nli","error":str(exc)})
# The reviewed English patient explanation is translated into the patient's
# selected language using the multilingual translation pipeline. NLLB produces
# the target-language text, while numeric, medication, script and semantic checks
# are collected so unsafe translation changes can be surfaced before release.
    source=result["patient_summary_en"] or ""
    if patient_language=="en":
        result["patient_summary_translated"]=source
        result["translation_quality"]="verified"
        result["translation_metadata"]={
            "numeric_preserved":True,"medication_preserved":True,"script_valid":True,
            "semantic_status":"source_language","semantic_score":1.0,
        }
    else:
        try:
            t=time.perf_counter()
            tx=await asyncio.to_thread(
                translation.translate_with_metadata,source,"en",patient_language,result["structured_data"]
            )
            result["patient_summary_translated"]=tx["translated"]
            result["translation_quality"]=tx["quality"]
            result["dose_sentences_for_review"]=tx["dose_sentences"]
            result["translation_metadata"]=tx
            result["model_metadata"]["translation"]={
                "model":settings.NLLB_MODEL,
                "seconds":round(time.perf_counter()-t,3),
                "target":patient_language,
            }
            # Any failed preservation or semantic check converts the translation result into
# a high-severity warning instead of treating the translated text as verified.
            bad=(
                not tx.get("numeric_preserved",False)
                or not tx.get("medication_preserved",False)
                or not tx.get("script_valid",False)
                or tx.get("semantic_status") not in {"pass","source_language"}
            )
            result["safety_checks"].append({
                "check_type":"translation_integrity",
                "status":"warning" if bad else "pass",
                "severity":"high" if bad else "low",
                "statement":f"{patient_language} translation",
                "evidence":tx.get("back_translation"),
                "score":tx.get("semantic_score"),
                "details":{k:v for k,v in tx.items() if k!="translated"},
                "resolved":not bad,
            })
        except Exception as exc:
            result["errors"].append({"stage":"translation","error":str(exc)})

   # The final preview stage converts the patient-language explanation into speech
# using the configured TTS route. Punjabi remains displayed in Shahmukhi but a
# Gurmukhi Punjabi rendering is generated internally for the Punjabi speech engine;
# other languages are passed to their own supported speech backends.
    tts_text=result["patient_summary_translated"] or result["patient_summary_en"]
    if tts_text:
        try:
            t=time.perf_counter()
            alternate=None
            # Punjabi speech uses a separate Gurmukhi rendering because the speech backend
# requires Punjabi script suitable for synthesis while the patient display remains
# in Shahmukhi.
            if patient_language=="pa_shah":
                alternate=await asyncio.to_thread(translation.translate_nllb,source,"en","pa")
            audio=await asyncio.to_thread(tts.synthesise,tts_text,patient_language,alternate)
            result["audio_summary_path"]=str(audio) if audio else None
            result["tts_backend"]=tts.backend_used(patient_language) if audio else "none"
            result["model_metadata"]["tts"]={
                "backend":result["tts_backend"],
                "seconds":round(time.perf_counter()-t,3),
                "language":patient_language,
            }
        except Exception as exc:
            result["errors"].append({"stage":"tts","error":str(exc)})

# Store the total pipeline time alongside the individual model timings so the
# performance of each AI stage and the complete consultation workflow can be
# evaluated separately.
    result["model_metadata"]["total_seconds"]=round(time.perf_counter()-started,3)
    return result
