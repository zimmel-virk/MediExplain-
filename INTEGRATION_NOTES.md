# MediExplain+ — Initial Project Enhanced Integration

This build uses the user's uploaded **initial MediExplain+ project as the source of truth**. The original AI/model and multilingual processing modules were retained from the uploaded `app.zip`; the integration adds workflow/UI/deployment features around that existing implementation.

## Preserved initial-project core

The following services are preserved from the uploaded initial backend implementation rather than replaced by the later rewrite:

- multilingual/code-switched faster-whisper STT and region-level merge logic;
- Urdu/Punjabi script handling and Shahmukhi conversion;
- NLLB translation and translation safety checks;
- Llama/Ollama structuring and patient explanation pipeline;
- DeBERTa NLI grounding;
- OCR and medication terminology/matching;
- deterministic medication scheduler;
- original TTS routes and medication-event voice audio;
- consultation, medication, schedule, share and cross-check APIs.

## Additive functionality integrated

- Professional role-aware application layout and navigation.
- Delegated **clinical assistant pre-review**. Treating doctors may either continue the original direct approval/release path or assign a case to an assistant. The assistant can only inspect an explicitly assigned case, complete a checklist, select **I have checked this case**, add notes and return it. The assistant cannot approve or release patient content; the treating doctor remains the final release gate.
- Support & Safety Centre for data-breach reports, technical problems, help requests and contact tickets.
- Multilingual Patient Learning Centre for English, Urdu and Punjabi Shahmukhi, with FAQs, portal/reminder guidance and small demo videos.
- Patient reminder page plus the original reminder manager mounted globally so alarms can fire while the patient navigates the portal.
- Enhanced patient PDF generated from the original released summary, doctor-confirmed medication table and original persisted medication schedules. It includes medication instructions, reminder timetable, follow-up, warning signs and glossary where available, with RTL Arabic-script PDF shaping support.
- Optional treating-doctor WhatsApp PDF delivery using the same generated released patient PDF. Real Meta WhatsApp credentials are required; the app does not fake successful delivery when unconfigured.
- AWS-oriented Docker/Nginx/CloudFront/WAF deployment scaffolding for an academic deployment. This does not imply HIPAA/GDPR certification or clinical-production approval.

## Original route compatibility

Static route comparison against the uploaded initial `app.zip` found:

- original backend API method/path pairs: **42**
- current backend API method/path pairs: **54**
- missing original routes: **0**
- additive routes: **12**

The added routes are limited to assistant review, support/learning, assistant discovery and optional WhatsApp PDF delivery.

## Data folder

The user's large original `backend/data` directory was not uploaded. This archive therefore includes the expected directory structure and `backend/data/README_IMPORT_YOUR_DATA.txt`, but cannot contain the user's unavailable database/recording/prescription bytes.

To reuse the original runtime data, copy the original `backend/data` contents into this project's `backend/data` directory before normal use. The new Alembic migration `0004_assistant_support` adds only the assistant-review and support-ticket tables on top of the existing schema.
