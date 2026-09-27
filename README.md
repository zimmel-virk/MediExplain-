# MediExplain+ Final Integrated FYP

**Secure Multilingual AI Consultation Summariser, Patient Explainer, Prescription Scheduler and Doctor Cross-Check Platform**

CM3020 Artificial Intelligence — Final Year Project  
Project template: **Orchestrating AI Models to Achieve a Goal**

> Academic research prototype. MediExplain+ does not diagnose, prescribe, or replace a clinician. Patient-facing content is released only through an explicit treating-doctor approval/release workflow.

I developed MediExplain+ as a multilingual healthcare AI prototype that combines several models rather than relying on one model for the whole task. The main aim was to help turn a recorded doctor-patient consultation into a reviewed clinical summary and a simpler patient explanation, while keeping the doctor in control of anything that is eventually shown to the patient. During development, I also added prescription OCR, medicine reconciliation, multilingual translation and audio, medication scheduling, and an optional second-doctor cross-check workflow.

## What this build includes

The original React/FastAPI workflow has been retained and upgraded rather than replaced:

- authenticated Doctor, Patient, Cross-Check Doctor and Admin roles;
- patient self-registration only (professional roles are admin-created/verified);
- backend-enforced object-level permissions;
- consent records and consent withdrawal;
- browser consultation recording with pause/resume, timer and input-level feedback;
- faster-whisper multilingual STT with code-switch passes;
- per-segment timestamps, confidence, low-confidence review flags;
- optional pyannote speaker diarisation;
- immutable raw transcript + reviewed transcript corrections;
- independent structured clinical extraction, SOAP draft and patient-friendly explanation;
- DeBERTa-v3 NLI grounding checks;
- unified safety checks with explicit clinician resolution;
- real medication terminology index using RxNorm Current Prescribable Content;
- optional DRAP CSV enrichment for Pakistan-specific registered brands/products;
- conservative medicine-name/brand/strength/form candidate matching;
- no automatic prescribed-dose invention;
- Tesseract + optional PaddleOCR prescription processing;
- editable OCR corrections and re-extraction;
- consultation-vs-prescription medication discrepancy warnings;
- mandatory doctor confirmation of medication identity/instructions;
- NLLB-200 translation for English, Urdu, Arabic, Punjabi, Pashto and Sindhi;
- Shahmukhi Punjabi display path without LLM medical-text polishing;
- translation number/medicine/script checks and optional NLI back-translation check;
- local-first MMS-TTS audio; cloud gTTS fallback is disabled by default;
- true Punjabi audio path for Shahmukhi display via Punjabi/Gurmukhi TTS input;
- final translation/audio generation and safety review before doctor approval; unresolved warnings block approval and release;
- deterministic medication schedules from doctor-confirmed instructions;
- Taken / Snooze / Skip medication events and multilingual voice reminders;
- patient PDF summaries;
- secure share links only after RELEASED;
- patient/doctor cross-check requests with assignment-scoped reviewer access;
- independent cross-check status and verdict; disagreement is never auto-resolved by AI;
- audit trail, portable local file storage and deterministic data erasure;
- Alembic migrations that preserve the original 13 demo consultations;
- evaluation harnesses for WER/MTER, translation, NLI, medication matching, OCR,
  readability, scheduling, privacy/security, performance, PDQI-9 and patient comprehension.

## One-time setup on your Mac

Requirements:
- macOS / Apple Silicon supported
- Python 3.11 recommended
- Node.js + npm
- Ollama
- Tesseract for prescription OCR

Install prerequisites if required:

```bash
brew install python@3.11 node ollama tesseract tesseract-lang
```

Then from this project root:

```bash
chmod +x setup_macos.sh run_macos.sh quickstart.sh
./setup_macos.sh
```

The setup script:
1. creates `backend/.venv`;
2. installs backend dependencies;
3. creates `backend/.env` with a random JWT secret;
4. upgrades the DB to the final Alembic schema;
5. preserves/seeds demo users;
6. downloads/imports the pinned RxNorm medication terminology if network access is available;
7. pulls `llama3.1:8b` into Ollama;
8. installs frontend dependencies.

### Optional full research extensions

Speaker diarisation and PaddleOCR are intentionally optional because their installation/model access is heavier:

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-optional.txt
```

For pyannote diarisation, accept the relevant Hugging Face model terms and place your token in:

```text
backend/.env
HF_TOKEN=...
```

To pre-download Whisper/NLLB/NLI/MMS-TTS weights:

```bash
cd backend
source .venv/bin/activate
python -m scripts.preload_models
```

Otherwise weights download lazily on first use.

## Run

From the project root:

```bash
./run_macos.sh
```

Open:

- App: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`

`quickstart.sh` is kept as a compatibility shortcut: it runs setup if required and then starts the application.

## Demo accounts

All seeded demo passwords are:

```text
demo1234
```

Examples:

```text
doctor@demo.com       Doctor
doctor2@demo.com      Doctor
reviewer@demo.com     Cross-check Doctor
patient.en@demo.com   English patient
patient.ur@demo.com   Urdu patient
patient.ar@demo.com   Arabic patient
patient.pa@demo.com   Punjabi/Shahmukhi patient
patient.ps@demo.com   Pashto patient
patient.sd@demo.com   Sindhi patient
admin@demo.com        Admin (created by the final seed script)
```

Local development databases, consultation recordings, generated patient files and runtime audio are intentionally excluded from the public repository. The setup and seed scripts create the required local database structure and demo data, while Alembic manages schema migrations.

## Final AI/model flow

```text
Consent
  ↓
Audio capture
  ↓
faster-whisper STT
  ├─ code-switch pass/merge
  ├─ segment confidence
  └─ optional speaker diarisation
  ↓
Immutable raw transcript
  ↓
Doctor transcript review
  ↓
Local Ollama Llama 3.1 8B
  ├─ structured clinical JSON
  ├─ independent SOAP draft
  └─ independent patient explanation
  ↓
DeBERTa-v3 NLI grounding
  ↓
Medication extraction
  ↓
RxNorm + optional DRAP terminology index
  ↓
Prescription image → OCR → editable OCR → medication reconciliation
  ↓
Safety dashboard
  ↓
Treating-doctor medication confirmation
  ↓
NLLB translation
  ├─ number preservation
  ├─ medication preservation
  ├─ script validation
  └─ back-translation/NLI when available
  ↓
Local MMS-TTS
  ↓
Final safety review and clinician resolution
  ↓
Treating-doctor final approval
  ↓
RELEASED
  ├─ patient text/audio/PDF
  ├─ medication schedules/reminders
  └─ optional assigned second-doctor cross-check
```

## Medication terminology

The former hand-built medication dictionary is **retired**.

The final service uses a local relational index populated from the pinned RxNorm Current Prescribable Content archive configured in `backend/app/core/config.py`. Run:

```bash
cd backend
source .venv/bin/activate
python -m scripts.setup_medication_data
```

For a DRAP CSV/export that you have lawfully obtained:

```bash
python -m scripts.setup_medication_data --skip-rxnorm --drap-csv /path/to/drap_export.csv
```

MediExplain+ treats terminology matches as **candidates for clinician verification**, not treatment advice. An unknown medicine is allowed to remain unresolved. The system never inserts a “common dose” as the patient's prescribed dose.

Check dataset status:

```bash
python - <<'PY'
from app.services.medication_index import stats
print(stats())
PY
```

## Important safety invariants

1. Raw STT is never silently overwritten by an LLM.
2. SOAP and patient explanation are generated independently.
3. Missing clinical information must remain missing/null rather than be invented.
4. Medication identity and medication instructions require explicit doctor confirmation.
5. OCR confidence, STT confidence, terminology-match confidence and doctor confirmation are separate concepts.
6. Unresolved safety warnings block doctor approval/release.
7. Translation integrity is checked again on the final doctor-approved text.
8. Patient/public access uses `released_at` as the durable release boundary.
9. Cross-check doctors can access only explicitly assigned cases.
10. Approved/released clinical data is immutable in-place.
11. PRN/ambiguous/missing-duration medication instructions never create invented fixed alarms.
12. The AI never resolves a disagreement between clinicians.

## Security and privacy measures

MediExplain+ includes several security and privacy controls appropriate for an academic healthcare AI prototype:

- role-based access control for Doctor, Patient, Assistant, Cross-Check Doctor and Admin users;
- backend-enforced object-level authorisation so users can only access consultations they are permitted to view;
- Amazon Cognito integration for cloud authentication;
- TOTP-based multi-factor authentication (MFA/2FA) support;
- dual authentication support for local development and Cognito-based deployment;
- password hashing for local authentication;
- protected API routes using authenticated access tokens;
- assignment-scoped access for assistants and cross-check doctors;
- explicit patient consent records and consent withdrawal;
- audit logging for important clinical, privacy and security actions;
- signed and short-lived sharing links for released patient summaries;
- patient-facing information is released only after the treating doctor's review and approval;
- sensitive environment files, deployment credentials, runtime databases, patient uploads and generated clinical files are excluded from the public repository;
- AWS deployment configuration includes restricted public-access controls and encrypted storage configuration.

The system was designed using HIPAA-aligned technical safeguards and GDPR-informed privacy controls. However, MediExplain+ remains an academic research prototype and does not claim regulatory certification, penetration-test certification or production clinical compliance.

### Authentication and access control

- Amazon Cognito authentication support;
- TOTP MFA/2FA;
- local JWT authentication for development;
- role-based and object-level permissions;
- protected doctor, patient, assistant and cross-check workflows;
- audit trail for security-sensitive actions.

## Database and storage

The final build uses:

```text
backend/data/mediexplain.db
backend/data/uploads/
backend/audio_cache/
backend/data/model_cache/
```

SQLite is managed with Alembic. On startup, the legacy database is adopted and upgraded safely.

Stored file references are relative, e.g.:

```text
audio_cache/ur_mms_abcd.wav
data/uploads/consultation_14.webm
```

not `/Users/...` paths. This makes the project movable between folders/laptops.

## Self-check

After setup:

```bash
cd backend
source .venv/bin/activate
python -m scripts.self_check
python -m unittest discover -s tests -v
```

The ZIP was built with the final migrations successfully tested both:
- against a fresh empty SQLite database; and
- against the original demo database while preserving the 13 existing consultations.

The pure unit suite covers storage portability, medication-matching safety, translation safety, anonymisation and scheduler behaviour.

## Evaluation

Install optional evaluation dependencies:

```bash
pip install -r evaluation/requirements.txt
```

Examples:

```bash
python evaluation/scripts/eval_scheduler.py
python evaluation/scripts/eval_medication_matcher.py
python evaluation/scripts/eval_readability.py
python evaluation/scripts/eval_stt.py
python evaluation/scripts/eval_translation.py
python evaluation/scripts/eval_nli.py
python evaluation/scripts/eval_ocr.py
python evaluation/scripts/eval_privacy.py
python evaluation/scripts/eval_performance.py
```

**No final human/clinical evaluation scores are fabricated in this repository.**
Scripts that require ground-truth audio, bilingual reference translations, clinician NLI labels, prescriptions, PDQI-9 ratings or patient-comprehension responses only produce final results after those real labels are supplied.

Historical pre-final evaluation JSON from the hand-built dictionary prototype is retained under:

```text
evaluation/legacy_baseline/
```

so it cannot be mistaken for final-system evidence.

## Evaluation data conventions

### STT
Place each recording and human reference together:

```text
evaluation/data/stt_audio/case01.wav
evaluation/data/stt_audio/case01.txt
evaluation/data/stt_audio/case01.lang
```

For code-switched tests, pass both primary/secondary language configuration when expanding the labelled manifest.

### Translation
`evaluation/data/translation_test_set.json` is created by the evaluation script if absent.
Use bilingual/clinician-validated references.

### NLI
Add labelled evidence/statement pairs to:

```text
evaluation/data/nli_test_set.json
```

### OCR
Place an image plus same-stem JSON ground truth under:

```text
evaluation/data/ocr/
```

### PDQI-9 and comprehension
Use the supplied rubrics/forms in:

```text
evaluation/rubrics/
```

## Project structure

```text
mediexplain/
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   ├── scripts/
│   ├── tests/
│   ├── data/
│   └── audio_cache/
├── frontend/
│   └── src/
├── evaluation/
├── docs/
├── setup_macos.sh
├── run_macos.sh
└── quickstart.sh
```

## Scope and regulatory wording

This is an academic prototype designed around privacy/security principles and human clinical oversight. It is **not** described as HIPAA-certified, GDPR-certified, or approved for clinical deployment. Formal organisational/legal controls such as Standard Contractual Clauses, hospital governance, production incident response and medical-device certification remain deployment concerns outside the academic software prototype.

