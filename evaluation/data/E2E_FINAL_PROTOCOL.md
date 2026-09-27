# MediExplain+ Final End-to-End Validation

The purpose of this evaluation is to verify that MediExplain+ operates
correctly as one integrated system rather than as isolated AI components.

No real patient-identifying information is required for this software test.

---

## E2E-01 — Mixed Urdu-English Full Consultation

Patient display language: Urdu

### Stage 1 — Authentication

- Doctor can log in
- Patient can log in
- Roles are displayed correctly

Result: PASS / FAIL

---

## Stage 2 — Consent

Doctor creates a consultation only after:

- Doctor consent = confirmed
- Patient consent = confirmed

The recording must not begin without the required consent.

Result: PASS / FAIL

---

## Stage 3 — Consultation Recording

Record a synthetic Urdu-English consultation.

Suggested software-test speech:

"مجھے دو دن سے بخار اور گلے میں درد ہے۔
The symptoms started two days ago.
For this software test the medication is paracetamol
500 milligrams twice daily for two days after food.
اگر علامات زیادہ خراب ہوں تو دوبارہ ڈاکٹر سے رابطہ کریں۔"

This is synthetic evaluation data and is not medical advice.

Result: PASS / FAIL

---

## Stage 4 — Speech Recognition

Verify:

- Urdu remains Urdu script
- English words are retained
- No Hindi/Devanagari appears
- Medication name retained
- 500 mg retained
- Twice daily retained
- Two days retained

Result: PASS / FAIL

---

## Stage 5 — Doctor Clinical View

Verify:

- Source transcript is available
- English clinical working representation is available where required
- Clinical summary is generated
- Symptoms are represented correctly
- Medication information is represented correctly
- No unsupported clinical fact is silently added

Result: PASS / FAIL

---

## Stage 6 — Safety

Verify:

- NLI/safety checks execute
- Low-confidence information can be flagged
- Medication information requires doctor confirmation
- Translation safety information is available
- Unresolved high-risk warnings prevent unsafe release

Result: PASS / FAIL

---

## Stage 7 — Medication

Verify extracted medication:

Medication: paracetamol / acetaminophen
Strength: 500 mg
Frequency: twice daily
Duration: two days
Food instruction: after food

Doctor confirms/corrects the medication before release.

Result: PASS / FAIL

---

## Stage 8 — Doctor Approval

Doctor reviews the patient-facing explanation.

Verify:

- Doctor can edit it
- Doctor can approve it
- Patient cannot access it before release
- Approved content becomes the authoritative patient content

Result: PASS / FAIL

---

## Stage 9 — Urdu Translation

Verify patient-facing Urdu output:

- Correct script
- No Devanagari
- Medication name preserved
- 500 mg preserved
- Twice-daily meaning preserved
- Two-day duration preserved
- Warning/follow-up meaning preserved

Result: PASS / FAIL

---

## Stage 10 — Spoken Summary

Verify:

- Patient summary audio is generated
- Audio is playable
- Urdu instructions are understandable
- Medication name is recognisable
- Dose is spoken correctly
- Frequency is spoken correctly

Result: PASS / FAIL

---

## Stage 11 — Patient Portal

Log in as the assigned patient.

Verify:

- Released consultation is visible
- Patient-friendly explanation is visible
- Raw clinical/internal information is hidden
- Patient cannot access another patient's consultation
- Summary audio can be played

Result: PASS / FAIL

---

## Stage 12 — Medication Schedule

Generate the medication schedule.

Expected:

twice daily × 2 days = 4 events

Verify:

- Four events generated
- Correct dates
- Correct times
- Medicine name correct
- Dose correct
- Frequency correct
- Duration correct

Result: PASS / FAIL

---

## Stage 13 — Medication Reminder

Verify:

- Alarm can work independently
- Voice can work independently
- Reminder shows medication information
- Taken works
- Snooze works
- Skip works

Result: PASS / FAIL

---

## Stage 14 — Cross-Check

Treating doctor requests a second opinion.

Verify:

- Unassigned reviewer cannot access case
- Assigned reviewer can access case
- Reviewer can submit verdict
- Treating doctor can view outcome
- Review cannot be submitted twice

Result: PASS / FAIL

---

## Stage 15 — Audit Trail

Verify important events are auditable, including as applicable:

- consent
- consultation creation
- processing
- approval
- release
- medication scheduling
- cross-check request
- cross-check submission

Audit data should not unnecessarily reproduce complete clinical content.

Result: PASS / FAIL

---

## Stage 16 — Final Security Boundary

Verify:

- Another patient cannot access the case
- Another doctor cannot modify/delete the case
- Unassigned reviewer cannot access the case
- Public user cannot access protected endpoints

Result: PASS / FAIL

---

## Final E2E Result

Stages passed: ____ / 16

Overall result:

PASS / FAIL

Critical failure present:

YES / NO

Comments:

____________________________________________________________

____________________________________________________________
