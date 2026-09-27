# MediExplain+ Master Evaluation Summary

## Completed measured evaluations

| Evaluation | Method | Result | Evidence |
|---|---|---:|---|
| Backend unit tests | Automated | 16/16 (100.0%) | software_unit_tests.json |
| Medication terminology regression | Automated regression | PASS | medication_matcher_final.json |
| Medication scheduler | Automated | 28/28 (100.0%) | scheduler.json |
| Privacy and access-control audit | Automated integration | 20/20 (100.0%) | privacy_audit_final.json |
| Cross-check workflow | Automated integration | 22/22 (100.0%) | cross_check.json |
| Full end-to-end workflow | Integrated + manual evidence | 30/30 (100.0%) | e2e.json |
| Patient portal display | Manual functional | 1/1 (100.0%) | e2e.json |
| Urdu summary audio playback | Manual functional | 1/1 (100.0%) | e2e.json |
| Medication alarm sound | Manual functional | 1/1 (100.0%) | e2e.json |
| Medication voice reminder | Manual functional | 1/1 (100.0%) | e2e.json |

## Formal evaluations still pending

| Evaluation | Required evidence |
|---|---|
| Speech-to-text accuracy | Requires 40 reference-labelled recordings: English, Urdu, Punjabi Shahmukhi, Pashto, Sindhi, Arabic, Urdu-English and Punjabi-English. Planned metrics: WER, CER, medication, number/dose and mixed-language Latin-token retention. |
| PDQI-9 clinical summary quality | Requires completed practising-doctor PDQI-9 ratings. |
| NLI grounding accuracy | Requires clinician-labelled supported/unsupported summary statements. |
| Translation quality | 50-case multilingual template prepared for Urdu, Punjabi Shahmukhi, Pashto, Sindhi and Arabic. Requires bilingual reference translations before BLEU/chrF and preservation results can be reported. |
| Prescription OCR | Requires 5 printed and 5 handwritten real prescription samples with ground truth. |
| Alarm manual checklist | Individual live alarm/voice functions were demonstrated, but the full formal 16-case manual checklist remains to be completed. |
| User accessibility/usability study | Requires real participant ratings; prepared evaluation form should be used rather than inferred scores. |

## Interpretation

The completed scored software/integration evaluations contain 116/116 passed checks.

**This must not be described as 100% clinical accuracy.** It represents the pass rate of the completed software and integration checks only.

STT accuracy, doctor-rated summary quality, clinician-labelled grounding, multilingual translation quality, OCR accuracy and participant usability remain separate empirical evaluations.
