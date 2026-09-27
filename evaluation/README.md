# Evaluation

This folder contains everything needed to evaluate MediExplain+ for the final
report. It has three parts:

```
evaluation/
├── METHODOLOGY.md          full methodology document (paste into report appendix)
├── scripts/                runnable evaluators
│   ├── eval_medication_matcher.py    ← runs against test set, fully automatic
│   ├── eval_readability.py           ← reads DB, computes Flesch-Kincaid etc.
│   ├── eval_privacy.py               ← integration tests against backend
│   ├── eval_stt.py                   ← needs labelled audio in data/stt_audio/
│   └── eval_translation.py           ← needs reference translations
├── data/
│   ├── medication_test_set.json      ← 50 pre-built test cases
│   ├── translation_test_set.json     ← starter template (fill in references)
│   └── stt_audio/                    ← put your labelled audio here
├── rubrics/
│   ├── pdqi9_rubric.md               ← give to doctor reviewers
│   └── patient_comprehension_form.md ← give to patient testers
└── results/                          ← evaluators write JSON here
```

## What you can run right now (no data collection needed)

These three give you real numbers within seconds:

```bash
cd backend
source .venv/bin/activate

# 1. Medication matcher — fully automated against 50 test cases
python ../evaluation/scripts/eval_medication_matcher.py

# 2. Readability of summaries in your DB (needs you to have run a few consultations)
pip install textstat
python ../evaluation/scripts/eval_readability.py

# 3. Privacy audit — integration tests against running backend
# (start backend first: uvicorn app.main:app --port 8000)
pip install httpx
python ../evaluation/scripts/eval_privacy.py
```

## What needs data collection

These need you to gather samples first, but the scripts compute the metrics
automatically once data is in place:

### STT evaluation

Drop your test audio files into `evaluation/data/stt_audio/`. For each
`my_audio.wav`, create:
- `my_audio.txt` containing the word-for-word reference transcript
- `my_audio.lang` (optional) containing the expected language code (`en`, `ur`, `pa_shah`, etc.)

Then:
```bash
pip install jiwer
python evaluation/scripts/eval_stt.py
```

### Translation evaluation

Run the script once to generate the template:
```bash
pip install sacrebleu
python evaluation/scripts/eval_translation.py
```

Then edit `evaluation/data/translation_test_set.json` and fill in the
`reference` field of each pair with a bilingual-doctor-validated translation.
Re-run the script.

## What requires human reviewers

These are rubric-based and need actual people:

- **PDQI-9 clinical note quality** — see `rubrics/pdqi9_rubric.md`. Three
  doctor reviewers each score 20 notes. Compute means + Krippendorff's α.
- **Patient comprehension** — see `rubrics/patient_comprehension_form.md`.
  15 patients × 5 MCQ questions per summary. Compute % correct.
- **Usability (SUS)** — use the standard 10-item SUS questionnaire; many
  free templates online.

For each rubric, transcribe the collected scores into a CSV/spreadsheet,
then summarise in your report.

## Suggested timeline

Realistic for a final-year project:

| Week | Activity |
|---|---|
| 1 | Run the three automated evaluators; document what you get |
| 2 | Collect 20 consultations of test audio + references (yourself or via simulation) |
| 3 | Run STT eval; build the translation reference set with one bilingual reviewer |
| 4 | Run translation eval; recruit doctor reviewers for PDQI-9 |
| 5 | PDQI-9 scoring; recruit patients for comprehension test |
| 6 | Patient comprehension + SUS sessions |
| 7 | Failure-mode analysis, writing up |

## A note on honesty

Examiners reward HONEST evaluation more than IMPRESSIVE evaluation. If a
metric misses the target, report it clearly with analysis of why. Do not
move the goalposts after seeing the result. The targets in `METHODOLOGY.md`
were set before any data collection.

If something fails badly — for example, NLLB produces a dangerous Urdu dose
translation — that's a finding, not a failure of the project. Document it,
catalogue it, propose mitigations. That section is often where the strongest
marks come from.
