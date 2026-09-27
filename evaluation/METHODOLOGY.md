# MediExplain+ — Evaluation Framework

This document defines the metrics and methods used to evaluate the prototype.
It accompanies the runnable evaluation scripts in `evaluation/scripts/`.

The evaluation is organised by **pipeline stage** so that failures can be
attributed to the right component, plus an end-to-end usability section.

---

## Summary table

| # | Stage | Metric | Type | Sample size |
|---|---|---|---|---|
| 1 | Speech-to-text | WER, MTER, language confidence | Quantitative | 20 consultations |
| 2 | Code-switching detection | Per-segment language accuracy | Quantitative | 10 mixed-language consultations |
| 3 | Clinical note quality | PDQI-9 | Qualitative (rubric) | 20 notes × 3 reviewers |
| 4 | Patient summary readability | Flesch-Kincaid Grade Level | Quantitative | 20 summaries |
| 5 | Patient summary comprehension | MCQ accuracy | Quantitative | 15 patients × 5 questions |
| 6 | Translation quality | BLEU, chrF, dose-safety audit | Quantitative + safety | 100 sentences/language |
| 7 | Medication extraction | Precision, Recall, F1 per field | Quantitative | 20 consultations |
| 8 | Medication matcher | Top-1, Top-3 accuracy | Quantitative | 50 noisy queries |
| 9 | OCR accuracy | Character/Word accuracy | Quantitative | 15 prescription images |
| 10 | TTS intelligibility | Listener MOS (1–5) + comprehension | Qualitative | 10 patients × 6 languages |
| 11 | End-to-end usability | SUS, task completion time | Qualitative + Quantitative | 5 doctors, 15 patients |
| 12 | Privacy & ethics | Pass/fail checklist | Compliance | 12-item audit |
| 13 | Safety analysis | Failure mode catalogue | Qualitative | open-ended |

---

## 1. Speech-to-text (STT) quality

### Metrics

**Word Error Rate (WER)** — the standard ASR metric.

$$ \text{WER} = \frac{S + D + I}{N} $$

where `S` = substitutions, `D` = deletions, `I` = insertions, `N` = words in reference.

Lower is better. Reported as a percentage. Industry benchmarks: <10% excellent,
10–20% usable, >25% problematic.

**Medical Term Error Rate (MTER)** — same as WER but computed *only* over a
curated list of medical terms (drug names, anatomical terms, dose units). A
10% overall WER that misses every drug name is worse than 15% WER with all
drugs correct.

**Language confidence** — Whisper's per-segment `language_probability`,
averaged across segments. Reported alongside WER so you can correlate failures
with low-confidence segments.

### Procedure

1. Collect or simulate 20 consultations (5–10 minutes each):
   - 5 English-only
   - 5 Urdu-only
   - 5 English+Urdu code-switched
   - 5 Punjabi-only (Shahmukhi-speaking patient + English-speaking doctor)
2. Have a bilingual human produce a word-for-word reference transcript.
3. Run each through three Whisper sizes (`base`, `small`, `medium`) — record
   WER, MTER, language probability, and runtime.

### Tooling

The `jiwer` Python library computes WER directly.

```python
from jiwer import wer, cer
score = wer(reference_text, hypothesis_text)
```

For MTER, run `wer()` over only the segments containing medical terms (the
script `eval_stt.py` includes a tagger that uses your medication database).

### Targets

| Group | WER target | MTER target |
|---|---|---|
| English-only | ≤ 10% | ≤ 5% |
| Urdu-only | ≤ 20% | ≤ 15% |
| Code-switched | ≤ 25% | ≤ 20% |
| Punjabi | ≤ 35% | report as baseline — no established target |

---

## 2. Code-switching detection

### Metric

**Per-segment language accuracy**: for each segment in the merged transcript
(after the dual-pass STT), check whether the assigned language matches the
ground-truth language that segment was actually spoken in.

$$ \text{accuracy} = \frac{\text{correctly tagged segments}}{\text{total segments}} $$

### Procedure

1. For each of the 5 code-switched consultations, annotate each ground-truth
   segment with its true language (e.g. `en` or `ur`).
2. Run the dual-pass STT with primary=`en`, secondary=`ur`.
3. Compare the system's per-segment language tag to ground truth.

### Target

≥ 70% per-segment accuracy on code-switched audio. This is a deliberately
modest target — true code-switching ASR is an open research problem.

---

## 3. Clinical note quality (PDQI-9)

### Metric

**PDQI-9** (Physician Documentation Quality Instrument). Nine dimensions
scored 1–5 each by an independent doctor reviewer:

1. **Up-to-date** — reflects all current findings
2. **Accurate** — no factual errors
3. **Thorough** — covers all relevant aspects
4. **Useful** — clinically helpful
5. **Organised** — logical structure
6. **Concise** — no redundant content
7. **Consistent** — internal consistency, no contradictions
8. **Succinct** — appropriately brief
9. **Internally consistent** — terminology used consistently

Total score range: 9 (worst) to 45 (best).

**Inter-rater reliability**: Krippendorff's alpha across the three reviewers.
α ≥ 0.6 = substantial agreement; ≥ 0.8 = strong.

### Procedure

1. Use the 20 consultations from Stage 1.
2. Three doctor reviewers independently score each AI-generated SOAP note.
3. Report mean + 95% CI per dimension and overall.

### Targets

- Mean overall PDQI-9 ≥ 35/45 (≈ 78%)
- Krippendorff's α ≥ 0.6

---

## 4. Patient summary readability

### Metric

**Flesch-Kincaid Grade Level (FKGL)**:

$$ \text{FKGL} = 0.39 \times \frac{\text{words}}{\text{sentences}} + 11.8 \times \frac{\text{syllables}}{\text{words}} - 15.59 $$

Lower = simpler.

Computed via the `textstat` library (only valid for English text — for non-
English outputs, see Stage 5 instead).

### Target

≤ Grade 6 (matches your slide's "6th-grade reading level" claim).

### Procedure

Run `textstat.flesch_kincaid_grade()` on the patient-friendly summary of each
of the 20 consultations. Report mean + distribution.

---

## 5. Patient comprehension test

### Metric

**MCQ accuracy** — multiple-choice comprehension questions answered correctly
after reading/listening to a summary.

Five questions per summary, fixed format:

1. What was the main problem the doctor discussed?
2. What medicine(s) were prescribed?
3. How often should you take medicine X?
4. What warning signs should make you call the doctor?
5. When is your follow-up?

Each question has one correct answer + three distractors. Score per patient
= correct/5. Aggregate mean = group comprehension rate.

### Procedure

Recruit 15 patients split across language groups (5 English, 5 Urdu, 5 other).
For each, present a doctor-approved summary in their language, then administer
the 5 MCQs verbally so literacy isn't a confound.

### Target

≥ 80% mean correctness across patients.

Also collect:
- "On a scale of 1–5, how confident are you about what to do next?"
- "On a scale of 1–5, how clear was the language?"
- "Did you prefer the text, audio, or both?"

---

## 6. Translation quality

### Metrics

**BLEU-4** (Bilingual Evaluation Understudy) — n-gram overlap with a reference
translation. Range 0–1. ≥ 0.30 ≈ usable for understanding; ≥ 0.50 ≈ good.

**chrF** (character F-score) — character-level F-measure. Better than BLEU
for morphologically rich languages like Urdu/Punjabi. Range 0–100. ≥ 50 ≈
usable; ≥ 65 ≈ good.

Computed via the `sacrebleu` library.

**Dose-safety audit** — binary classification of every translated sentence
that contains a numeric value:
- **safe** = the dose translated correctly
- **inaccurate** = wrong number or wrong unit, but doesn't reverse meaning
- **dangerous** = could harm the patient (e.g. "twice daily" became "twice an hour")

Reported as: % safe / % inaccurate / % dangerous. The goal is **zero**
dangerous sentences.

### Procedure

1. Take 100 sentences sampled from doctor-approved English patient summaries.
2. A bilingual doctor produces a reference translation in each target language
   (Urdu, Punjabi-Shahmukhi, Arabic).
3. Run NLLB-200 translation; compute BLEU + chrF per language.
4. Separately, the bilingual doctor classifies each numeric sentence as safe /
   inaccurate / dangerous.

### Targets

| Language | BLEU target | chrF target | Dangerous count |
|---|---|---|---|
| Urdu | ≥ 0.30 | ≥ 55 | 0 |
| Arabic | ≥ 0.30 | ≥ 55 | 0 |
| Punjabi (Shahmukhi) | ≥ 0.20 | ≥ 45 | 0 |
| Pashto, Sindhi | report as baseline | report as baseline | 0 |

The "dangerous = 0" target is non-negotiable. If any dangerous translations
appear in evaluation, they MUST be reported in the failure-analysis section,
with mitigation proposals.

---

## 7. Structured extraction (medications, warnings, glossary)

### Metrics

**Per-field precision, recall, F1** for medications:

- **TP** = medication correctly extracted with all fields matching ground truth
- **PartialTP** = name correct but ≥1 detail wrong (counted as 0.5 weight)
- **FP** = medication in AI output but not in ground truth (hallucination)
- **FN** = medication in ground truth but missing from AI output

$$ \text{Precision} = \frac{TP + 0.5 \cdot PartialTP}{TP + PartialTP + FP} $$
$$ \text{Recall} = \frac{TP + 0.5 \cdot PartialTP}{TP + PartialTP + FN} $$

Same metrics computed separately for warning signs and glossary entries.

### Procedure

For each of the 20 consultations:
1. A doctor lists ground-truth medications with `{name, dose, frequency, duration}`.
2. Compare to LLM output. Compute precision/recall/F1 on `name` and on each
   detail field.
3. Maintain a catalogue of every hallucinated medication.

### Targets

| Field | Precision | Recall |
|---|---|---|
| Medication name | ≥ 0.95 | ≥ 0.90 |
| Dose | ≥ 0.80 | ≥ 0.75 |
| Frequency | ≥ 0.80 | ≥ 0.75 |
| Duration | ≥ 0.75 | ≥ 0.70 |
| Warning signs | ≥ 0.85 | ≥ 0.75 |

**Any hallucinated medication must be listed individually in the report.**

---

## 8. Medication matcher accuracy

This evaluates the fuzzy-match service that powers the "did you mean…"
suggestions.

### Metrics

**Top-1 accuracy** — for each noisy input, does the top suggestion equal the
true generic name?

**Top-3 accuracy** — does the true generic appear anywhere in the top 3?

**Mean reciprocal rank (MRR)** — average of 1/rank of the correct answer.
Closer to 1.0 = correct answers are usually first.

### Procedure

Use a test set of 50 noisy queries with known correct answers. Categories:

- Common misspellings: `paracitamol`, `azithromicin`, `metformine`
- Phonetic variants: `panadole`, `brufeen`, `asprin`
- Brand names: `Augmentin`, `Lipitor`, `Glucophage`
- Urdu-script: `پیناڈول`, `بروفین`, `پیراسیٹامول`
- Short forms: `cipro` (for ciprofloxacin), `metro` (for metronidazole)
- Hard negatives: `headache`, `painkiller`, `tablet` (should return *low-score*
  results or none)

The full test set is in `evaluation/data/medication_test_set.json` and the
runner script computes all three metrics automatically.

### Targets

- Top-1 ≥ 0.80 (true name is the top suggestion)
- Top-3 ≥ 0.95 (true name appears in first 3)
- MRR ≥ 0.85
- Hard negatives: ≤ 10% return high-confidence false matches

---

## 9. OCR accuracy

### Metrics

**Character accuracy** = 1 − CER (Character Error Rate)
**Word accuracy** = 1 − WER, on prescription text

### Procedure

15 prescription images:
- 5 printed (pharmacy-typed)
- 5 well-handwritten (clear practitioner handwriting)
- 5 difficult (rushed handwriting, faded, photographed at angle)

For each: human transcribes ground truth, compare against Tesseract output.

### Targets

| Category | Character accuracy | Word accuracy |
|---|---|---|
| Printed | ≥ 0.95 | ≥ 0.90 |
| Handwritten (clear) | ≥ 0.75 | ≥ 0.60 |
| Handwritten (difficult) | report as baseline | report as baseline |

Honest framing in the report: **handwritten prescription OCR is an open
research problem**. The system flags low-confidence OCR (< 50%) and asks the
doctor to retype manually — that fallback workflow is itself part of the
evaluation.

---

## 10. TTS intelligibility

### Metric

**Mean Opinion Score (MOS)** — listeners rate audio on a 1–5 scale for
naturalness and clarity. Industry-standard subjective TTS metric.

**Comprehension check** — separate from naturalness: can the listener
understand the content? Boolean per phrase.

### Procedure

10 patients per language. Each listens to 5 generated summaries in their
preferred language. After each:
- Rate naturalness (1 = "robotic, hard to listen to" → 5 = "natural human voice")
- Rate clarity (1 = "couldn't understand most words" → 5 = "every word clear")
- Answer one comprehension question about the content

Report mean ± SD per language.

### Targets

| Language | Backend | MOS target | Comprehension |
|---|---|---|---|
| English | gTTS | ≥ 3.5 | ≥ 90% |
| Urdu | gTTS | ≥ 3.5 | ≥ 85% |
| Arabic | gTTS | ≥ 3.5 | ≥ 85% |
| Punjabi (Shahmukhi → Urdu voice) | gTTS-urdu | ≥ 3.0 | ≥ 75% |
| Pashto, Sindhi | MMS-TTS | ≥ 2.5 | ≥ 65% |

The lower targets for non-gTTS languages reflect honest expectations of MMS
quality — robotic but understandable.

---

## 11. End-to-end usability

### Doctor side (5 doctors, 4 consultations each)

- **System Usability Scale (SUS)** — standard 10-item Likert questionnaire,
  scored 0–100. Industry average ≈ 68.
- **Documentation time reduction**: time-to-finalised-note via MediExplain+
  vs. doctor's normal workflow (paper notes or other software).
- **Free-form**: "What would prevent you from using this in real practice?"

### Patient side (15 patients)

- **SUS**
- "Did the summary tell you what you needed to know?" yes / partial / no
- "Would you prefer text, audio, or both?"
- "Would you trust this enough to follow without re-asking the doctor?" 1–5

### Targets

- Doctor SUS ≥ 68
- Patient SUS ≥ 68
- Documentation time reduction ≥ 30%
- Trust score ≥ 3.5

---

## 12. Privacy & ethics audit

A pass/fail checklist for the privacy controls the slides committed to:

| # | Check | Test method | Pass criterion |
|---|---|---|---|
| 1 | Consent gate cannot be bypassed | curl POST /consultations with both consents=false | API returns 400 |
| 2 | Audit log captures every state change | Create→approve→release→delete, inspect audit_logs table | 4 distinct rows for the cycle |
| 3 | Patient cannot read other patients' data | Login as A, GET /consultations/{B's id} | Returns 403 |
| 4 | Doctor cannot edit another doctor's case | Login as Doc1, POST approve on Doc2's case | Returns 403 |
| 5 | Cross-check doctor cannot see un-requested cases | Login as reviewer, list cross-checks | Only assigned cases visible |
| 6 | Deletion removes audio files | Create with audio, DELETE, check filesystem | File gone |
| 7 | Deletion preserves audit record | After DELETE, query audit_logs | Action record present |
| 8 | Anonymisation strips PII | Pass test strings to `anonymise()` | Phones, emails, CNICs replaced |
| 9 | Share token expires | Generate token, wait > expiry, attempt access | Returns 401 |
| 10 | Share token scoped to one consultation | Use token for consultation A on consultation B | Returns 401 |
| 11 | Patient sees only released/cross-checked cases | Login as patient, list | No DRAFTED/APPROVED in list |
| 12 | Password hashing not reversible | Inspect DB | hashed_password starts with bcrypt prefix `$2b$` |

Target: 12/12 pass. Any fail is a blocking issue for the project.

The script `eval_privacy.py` automates checks 1–11.

---

## 13. Failure mode analysis (qualitative)

This is the section that distinguishes a 2.1 evaluation from a first-class one.

For each pipeline stage, catalogue **the 3–5 most interesting failures
encountered**. For each failure:

- Input that triggered it (with audio file / image reference)
- System output
- Expected output
- Stage that failed (STT / LLM / translation / OCR / TTS)
- Severity (cosmetic / annoying / safety-relevant)
- Root cause hypothesis
- Proposed mitigation (added to roadmap)

Examiners reward candidates who can clearly say *"my system fails in this
specific way, and here's why and how I'd fix it"* far more than candidates
who claim everything worked perfectly.

---

## Sample size justification

Why 20 / 15 / 5 / 100?

- **20 consultations**: enough to detect a 0.5-point shift in mean PDQI-9 at
  α=0.05, given typical within-doctor variance of ~0.8. Standard sample
  size for HCI work in clinical NLP.
- **15 patients**: 5 MCQs each = 75 datapoints, gives a reasonable 95% CI on
  a proportion around 0.8 (±9 percentage points).
- **5 doctors**: matches Nielsen's "5 users find 80% of usability problems"
  heuristic; typical for clinical HCI literature.
- **100 sentences for translation**: large enough for stable BLEU/chrF
  estimates; small enough for one bilingual reviewer to validate in a day.
- **50 medication test cases**: covers all the noise categories with enough
  per-category samples for stable Top-1 / Top-3 estimates.

The report should explicitly note these are minimum viable sample sizes and
that larger studies would be needed before any deployment.

---

## What to report

For each metric: **mean, distribution, 95% CI, comparison to target, and
honest commentary** when the target is missed. Use box plots over bar charts
where the distribution matters (it usually does).

Recommended structure for the Evaluation chapter:

1. Methodology (this document, condensed)
2. Stage-by-stage results with the targets table front and centre
3. **Failure analysis** — pick the most interesting failures
4. Threats to validity (small N, simulated consultations, language coverage)
5. What would need to change for a real clinical trial
