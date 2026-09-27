# MediExplain+ Final Build Verification

Build date: 10 August 2026

## Verified in the artifact build

- Python source compilation: **PASS**
- Shell script syntax (`setup_macos.sh`, `run_macos.sh`, `quickstart.sh`): **PASS**
- Backend unit tests: **16/16 PASS**
- Deterministic medication scheduler evaluation: **9/9 PASS**
- Fresh empty SQLite database migration: **PASS** through `0003_schema_constraints`
- Preserved legacy/demo database migration: **PASS** at `0003_schema_constraints`
- Alembic model/schema drift check: **PASS** (`No new upgrade operations detected`)
- Existing demo data preserved: **9 users, 13 consultations, 6 cross-check requests, 152 historical audit events**
- Migrated final records: **13 consent records, 27 summary versions, 12 consultation-medication records**
- Portable storage references: **PASS** (0 absolute `/Users/...` paths)
- Existing runtime file references: **29 checked, 0 missing**
- Frontend package/lock JSON: **valid**
- Frontend relative source imports: **0 missing**
- Generated dependency folders are intentionally excluded (`node_modules`, `.venv`, model weights).

## Runtime/model verification boundary

This execution environment cannot install packages from the public Python/npm registries, so a complete browser-to-model end-to-end run could not be repeated inside the artifact sandbox. The source includes a one-command macOS bootstrap that installs the declared dependencies, imports the pinned RxNorm terminology release, pulls the Ollama model, migrates the database, seeds demo accounts, and installs the frontend.

The project does **not** invent clinician/patient study results. WER, PDQI-9, multilingual translation, NLI, OCR, comprehension, usability and privacy evaluation scripts/datasets are included so those empirical results can be generated from real labelled/test data.

## Safety invariants implemented

- Public self-registration is patient-only.
- Professional/admin accounts require admin creation/verification.
- Consultation access uses object-level authorization.
- Reviewers only access assigned cases.
- Patient/public delivery requires a durable release boundary.
- Raw STT is preserved; corrections are separate.
- SOAP, structured extraction and patient explanation are separate operations.
- Safety warnings must be resolved before release.
- Medicine identity/instructions require explicit clinician confirmation.
- Terminology matching never fills a patient dose from reference data.
- Fixed reminder schedules are generated only from confirmed medicines after release.
- Released clinical source data is immutable.
- File references are relative/portable and protected from traversal.
- Deletion removes associated protected artifacts while retaining a minimal audit event.
