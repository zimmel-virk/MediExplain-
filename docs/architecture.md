# Final architecture

MediExplain+ is a layered local-first web application.

## Presentation
React/Vite provides role-specific views for treating doctors, patients and assigned cross-check reviewers. Route guards improve UX; backend authorization remains the security boundary.

## Application/API
FastAPI owns authentication, consent, workflow state, object authorization, audit events, file access, clinical approval/release, cross-checking and medication schedule endpoints.

## Orchestration
`app/services/orchestrator.py` coordinates independent AI stages. Raw STT is immutable. Structured extraction, SOAP, patient explanation, NLI, translation and TTS are separate calls/modules rather than one opaque LLM output.

## Data
SQLAlchemy + SQLite store prototype data. Alembic owns schema evolution. Generated/uploaded files are protected local files referenced by portable paths.

## AI stages
1. faster-whisper — multilingual speech recognition.
2. Optional pyannote — speaker diarisation.
3. Ollama Llama 3.1 8B — constrained structured extraction, SOAP draft, patient explanation.
4. DeBERTa-v3 NLI — source grounding.
5. RxNorm + optional DRAP import — medication terminology candidates.
6. Tesseract / optional PaddleOCR — prescription OCR.
7. NLLB-200 — translation.
8. MMS-TTS — local spoken output.

## Safety gates
- consent before audio upload;
- segment uncertainty visible to doctor;
- immutable raw transcript;
- explicit transcript review;
- medicine candidates never auto-prescribe;
- doctor confirms medication identity/instructions;
- unresolved summary/translation safety warnings block progression;
- doctor approves source summary;
- final translation/audio generated from approved content;
- explicit release creates patient access;
- reviewer access requires a CrossCheck assignment.

## Consultation lifecycle

`recording → transcribing → transcript_review → summarising → safety_check → drafted/safety_review_required → approved → released → optional under_cross_check/cross_checked`

Failure is explicit (`processing_failed`) rather than silent downstream continuation.

## Portability
The database stores `audio_cache/...` and `data/uploads/...`, never developer-machine absolute paths. This prevents the path regression that broke multilingual audio when the project folder was moved.
