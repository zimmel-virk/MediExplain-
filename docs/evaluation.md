# Final evaluation plan

The repository separates **software verification** from **empirical AI/clinical evaluation**.

## Already executable without participant data
- backend unit tests;
- database migration tests;
- portable-path checks;
- deterministic medication-scheduler accuracy;
- live privacy/object-authorization audit.

## Requires labelled final data
### Speech-to-text
WER, CER, medical-term error rate, code-switch retention, medication-name retention, dose/number accuracy; report by language and recording condition.

### Summary
PDQI-9 ratings from clinicians, factual completeness/grounding, readability, editing burden and approval rate.

### NLI safety
Clinician-labelled entailment/neutral/contradiction pairs; precision, recall and F1 with particular attention to false negatives.

### Medication terminology
Independent misspellings/brands/hard negatives not inserted into the terminology index. Report top-1/top-3 and hard-negative false-positive rate.

### Prescription OCR
Printed and handwritten prescriptions separately. Report WER/CER plus medicine/strength/frequency/duration field accuracy.

### Translation
BLEU/chrF and optional COMET plus bilingual human evaluation. Separately report number, medicine, negation and script preservation.

### TTS/patient comprehension
Intelligibility, medicine/number pronunciation and patient questions covering medicine, dose, frequency, follow-up and warning signs.

### Performance
Stage-level latency is recorded in `model_metadata`. Report model/runtime/hardware and end-to-end time.

## Integrity rule
Historical pre-final results are under `evaluation/legacy_baseline/`. They must not be presented as final-system results. Empty final datasets remain empty until real measurements are collected.
