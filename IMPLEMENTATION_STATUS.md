# Implementation status — final software build

| Area | Software implementation |
|---|---|
| Clean paths + migrations | Complete |
| Authentication + verified roles | Complete |
| Backend RBAC/object authorization | Complete |
| Consent record + withdrawal | Complete |
| Portable storage + erasure | Complete |
| Recording pause/resume/meter | Complete |
| faster-whisper STT | Complete |
| Code-switch merge | Complete; empirical accuracy pending |
| Segment confidence | Complete |
| Speaker diarisation | Implemented as optional pyannote extension |
| Immutable/reviewed transcript | Complete |
| Structured clinical extraction | Complete |
| Independent SOAP | Complete |
| Independent patient explanation | Complete |
| NLI grounding | Complete; labelled evaluation pending |
| Real medication terminology | RxNorm importer complete; optional DRAP importer complete |
| Conservative fuzzy matching | Complete |
| Prescription OCR/edit/re-extract | Complete |
| Medication discrepancy checks | Complete |
| Mandatory medication confirmation | Complete |
| Translation | Complete |
| Script/number/medicine/semantic checks | Complete |
| Local multilingual TTS | Complete |
| Doctor approval/release gate | Complete |
| Medication schedules/events | Complete |
| Voice reminders | Complete |
| Cross-check assignment/verdict/conflict | Complete |
| Audit trail | Complete |
| PDF/share | Complete |
| Evaluation harness | Complete |
| Human/clinician data collection | Must be performed with real participants/data; not fabricated |

## Build verification performed for this ZIP

- Python source compilation: passed.
- Final Alembic migration against a copy of the original active DB: passed; 13 consultations preserved.
- Final Alembic migration from an empty DB: passed.
- Stored consultation/audio/prescription path migration: 0 missing referenced files in the included demo dataset.
- Pure unit tests: 16/16 passed.
- Deterministic scheduler evaluation: 9/9 cases passed.
- Frontend dependency build could not be executed in the artifact sandbox because its internal npm mirror lacked a transitive package; `npm install` is left to the supplied macOS setup script using the user's normal npm registry.
