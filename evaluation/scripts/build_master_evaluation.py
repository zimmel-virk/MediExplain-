#!/usr/bin/env python3

import csv
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evaluation" / "results"

OUT_JSON = RESULTS / "master_evaluation_summary.json"
OUT_CSV = RESULTS / "master_evaluation_summary.csv"
OUT_MD = RESULTS / "master_evaluation_summary.md"


# ---------------------------------------------------------
# VERIFIED RESULTS
# Only results actually measured during this project are
# recorded here. Missing clinical/user studies remain pending.
# ---------------------------------------------------------

rows = [
    {
        "phase": "Software verification",
        "evaluation": "Backend unit tests",
        "type": "Automated",
        "status": "PASS",
        "passed": 16,
        "total": 16,
        "accuracy": 100.0,
        "evidence": "software_unit_tests.json",
        "notes": (
            "Anonymisation, medication matching, scheduler, "
            "secure storage and translation-safety unit tests."
        ),
    },
    {
        "phase": "16E",
        "evaluation": "Medication terminology regression",
        "type": "Automated regression",
        "status": "PASS",
        "passed": None,
        "total": None,
        "accuracy": 100.0,
        "evidence": "medication_matcher_final.json",
        "notes": (
            "Development/regression dataset only. "
            "Top-1, Top-3 and Top-5 matching reached 100%; "
            "strength preservation 100%; hard-negative false-positive "
            "rate 0%. Not presented as an unbiased held-out final result."
        ),
    },
    {
        "phase": "16G",
        "evaluation": "Medication scheduler",
        "type": "Automated",
        "status": "PASS",
        "passed": 28,
        "total": 28,
        "accuracy": 100.0,
        "evidence": "scheduler.json",
        "notes": (
            "English, Urdu, Punjabi Shahmukhi, mixed-language, "
            "clinical abbreviations, PRN and unsupported/missing "
            "instruction cases."
        ),
    },
    {
        "phase": "16H",
        "evaluation": "Privacy and access-control audit",
        "type": "Automated integration",
        "status": "PASS",
        "passed": 20,
        "total": 20,
        "accuracy": 100.0,
        "evidence": "privacy_audit_final.json",
        "notes": (
            "Authentication, consent, RBAC, patient isolation, "
            "cross-check authorization, deletion, audit retention, "
            "password hashing and share-token protection."
        ),
    },
    {
        "phase": "16H",
        "evaluation": "Cross-check workflow",
        "type": "Automated integration",
        "status": "PASS",
        "passed": 22,
        "total": 22,
        "accuracy": 100.0,
        "evidence": "cross_check.json",
        "notes": (
            "Reviewer assignment, authorization, pending/completed "
            "workflow, persisted verdict/comments and audit trail."
        ),
    },
    {
        "phase": "17",
        "evaluation": "Full end-to-end workflow",
        "type": "Integrated + manual evidence",
        "status": "PASS",
        "passed": 30,
        "total": 30,
        "accuracy": 100.0,
        "evidence": "e2e.json",
        "notes": (
            "Consultation 40: consent → audio → multilingual STT → "
            "clinical explanation → safety review → medication → "
            "doctor approval → Urdu translation → TTS → release → "
            "scheduler → patient portal → cross-check → audit."
        ),
    },

    # -----------------------------------------------------
    # MANUALLY OBSERVED PATIENT-SIDE FEATURES
    # -----------------------------------------------------

    {
        "phase": "17",
        "evaluation": "Patient portal display",
        "type": "Manual functional",
        "status": "PASS",
        "passed": 1,
        "total": 1,
        "accuracy": 100.0,
        "evidence": "e2e.json",
        "notes": (
            "Released Urdu summary and medication schedule visible; "
            "internal clinical/model information not exposed."
        ),
    },
    {
        "phase": "17",
        "evaluation": "Urdu summary audio playback",
        "type": "Manual functional",
        "status": "PASS",
        "passed": 1,
        "total": 1,
        "accuracy": 100.0,
        "evidence": "e2e.json",
        "notes": "Patient-side Urdu summary audio played successfully.",
    },
    {
        "phase": "17",
        "evaluation": "Medication alarm sound",
        "type": "Manual functional",
        "status": "PASS",
        "passed": 1,
        "total": 1,
        "accuracy": 100.0,
        "evidence": "e2e.json",
        "notes": "Alarm test worked in the patient reminder interface.",
    },
    {
        "phase": "17",
        "evaluation": "Medication voice reminder",
        "type": "Manual functional",
        "status": "PASS",
        "passed": 1,
        "total": 1,
        "accuracy": 100.0,
        "evidence": "e2e.json",
        "notes": "Spoken medication reminder test worked.",
    },

    # -----------------------------------------------------
    # PENDING FORMAL EVALUATIONS
    # No scores are fabricated.
    # -----------------------------------------------------

    {
        "phase": "16A",
        "evaluation": "Speech-to-text accuracy",
        "type": "Clinical/data evaluation",
        "status": "PENDING",
        "passed": None,
        "total": None,
        "accuracy": None,
        "evidence": "",
        "notes": (
            "Requires 40 reference-labelled recordings: English, Urdu, "
            "Punjabi Shahmukhi, Pashto, Sindhi, Arabic, Urdu-English "
            "and Punjabi-English. Planned metrics: WER, CER, medication, "
            "number/dose and mixed-language Latin-token retention."
        ),
    },
    {
        "phase": "16B",
        "evaluation": "PDQI-9 clinical summary quality",
        "type": "Doctor-rated",
        "status": "PENDING",
        "passed": None,
        "total": None,
        "accuracy": None,
        "evidence": "",
        "notes": "Requires completed practising-doctor PDQI-9 ratings.",
    },
    {
        "phase": "16C",
        "evaluation": "NLI grounding accuracy",
        "type": "Clinician-labelled",
        "status": "PENDING",
        "passed": None,
        "total": None,
        "accuracy": None,
        "evidence": "",
        "notes": (
            "Requires clinician-labelled supported/unsupported "
            "summary statements."
        ),
    },
    {
        "phase": "16D",
        "evaluation": "Translation quality",
        "type": "Reference + automatic",
        "status": "PENDING",
        "passed": None,
        "total": None,
        "accuracy": None,
        "evidence": "",
        "notes": (
            "50-case multilingual template prepared for Urdu, "
            "Punjabi Shahmukhi, Pashto, Sindhi and Arabic. "
            "Requires bilingual reference translations before "
            "BLEU/chrF and preservation results can be reported."
        ),
    },
    {
        "phase": "16F",
        "evaluation": "Prescription OCR",
        "type": "Document evaluation",
        "status": "PENDING",
        "passed": None,
        "total": None,
        "accuracy": None,
        "evidence": "",
        "notes": (
            "Requires 5 printed and 5 handwritten real prescription "
            "samples with ground truth."
        ),
    },
    {
        "phase": "16G",
        "evaluation": "Alarm manual checklist",
        "type": "Manual functional",
        "status": "PENDING",
        "passed": None,
        "total": 16,
        "accuracy": None,
        "evidence": "",
        "notes": (
            "Individual live alarm/voice functions were demonstrated, "
            "but the full formal 16-case manual checklist remains to "
            "be completed."
        ),
    },
    {
        "phase": "16I",
        "evaluation": "User accessibility/usability study",
        "type": "Participant-rated",
        "status": "PENDING",
        "passed": None,
        "total": None,
        "accuracy": None,
        "evidence": "",
        "notes": (
            "Requires real participant ratings; prepared evaluation "
            "form should be used rather than inferred scores."
        ),
    },
]


# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------

completed = [
    r for r in rows
    if r["status"] == "PASS"
]

pending = [
    r for r in rows
    if r["status"] == "PENDING"
]

automated_scored = [
    r for r in completed
    if r["passed"] is not None
    and r["total"] is not None
    and r["type"] not in {
        "Manual functional",
    }
]

total_passed = sum(
    r["passed"]
    for r in automated_scored
)

total_checks = sum(
    r["total"]
    for r in automated_scored
)


summary = {
    "project": "MediExplain+",
    "generated_at": datetime.now().isoformat(),
    "completed_evaluations": len(completed),
    "pending_formal_evaluations": len(pending),
    "verified_scored_checks_passed": total_passed,
    "verified_scored_checks_total": total_checks,
    "verified_scored_check_rate_percent": (
        round(
            total_passed / total_checks * 100,
            1,
        )
        if total_checks
        else None
    ),
    "important_note": (
        "The combined check rate is a software verification summary, "
        "not a clinical accuracy figure. Pending STT, PDQI-9, NLI, "
        "translation, OCR and participant evaluations must be reported "
        "separately when real data are collected."
    ),
    "results": rows,
}


OUT_JSON.write_text(
    json.dumps(
        summary,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)


# ---------------------------------------------------------
# CSV
# ---------------------------------------------------------

fields = [
    "phase",
    "evaluation",
    "type",
    "status",
    "passed",
    "total",
    "accuracy",
    "evidence",
    "notes",
]

with OUT_CSV.open(
    "w",
    encoding="utf-8",
    newline="",
) as f:
    writer = csv.DictWriter(
        f,
        fieldnames=fields,
    )

    writer.writeheader()

    for row in rows:
        writer.writerow(row)


# ---------------------------------------------------------
# MARKDOWN REPORT TABLE
# ---------------------------------------------------------

lines = [
    "# MediExplain+ Master Evaluation Summary",
    "",
    "## Completed measured evaluations",
    "",
    "| Evaluation | Method | Result | Evidence |",
    "|---|---|---:|---|",
]

for r in completed:
    if (
        r["passed"] is not None
        and r["total"] is not None
    ):
        result = (
            f"{r['passed']}/{r['total']} "
            f"({r['accuracy']:.1f}%)"
        )
    else:
        result = "PASS"

    lines.append(
        f"| {r['evaluation']} "
        f"| {r['type']} "
        f"| {result} "
        f"| {r['evidence'] or 'Manual evidence'} |"
    )


lines += [
    "",
    "## Formal evaluations still pending",
    "",
    "| Evaluation | Required evidence |",
    "|---|---|",
]

for r in pending:
    lines.append(
        f"| {r['evaluation']} | {r['notes']} |"
    )


lines += [
    "",
    "## Interpretation",
    "",
    (
        f"The completed scored software/integration evaluations "
        f"contain {total_passed}/{total_checks} passed checks."
    ),
    "",
    (
        "**This must not be described as 100% clinical accuracy.** "
        "It represents the pass rate of the completed software and "
        "integration checks only."
    ),
    "",
    (
        "STT accuracy, doctor-rated summary quality, clinician-labelled "
        "grounding, multilingual translation quality, OCR accuracy and "
        "participant usability remain separate empirical evaluations."
    ),
]

OUT_MD.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8",
)


print()
print("=" * 74)
print("MediExplain+ Master Evaluation Summary")
print("=" * 74)
print()
print(f"Completed evaluations:       {len(completed)}")
print(f"Pending formal evaluations:  {len(pending)}")
print()
print(
    "Verified scored checks:     "
    f"{total_passed}/{total_checks}"
)
print(
    "Software check pass rate:   "
    f"{summary['verified_scored_check_rate_percent']:.1f}%"
)
print()
print("IMPORTANT:")
print(
    "This is a software/integration pass rate, "
    "NOT a clinical accuracy percentage."
)
print()
print(f"JSON: {OUT_JSON}")
print(f"CSV:  {OUT_CSV}")
print(f"MD:   {OUT_MD}")
