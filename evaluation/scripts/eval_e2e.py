#!/usr/bin/env python3

import json
import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "backend" / "data" / "mediexplain.db"
MANUAL = ROOT / "evaluation" / "data" / "e2e_manual_checks.json"
OUT = ROOT / "evaluation" / "results" / "e2e.json"

CID = 40


def row_dict(row):
    return dict(row) if row is not None else None


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    consultation = conn.execute(
        """
        SELECT *
        FROM consultations
        WHERE id=?
        """,
        (CID,),
    ).fetchone()

    if not consultation:
        raise SystemExit(
            f"Consultation {CID} not found."
        )

    c = row_dict(consultation)

    segments = [
        row_dict(r)
        for r in conn.execute(
            """
            SELECT *
            FROM transcript_segments
            WHERE consultation_id=?
            ORDER BY segment_index
            """,
            (CID,),
        ).fetchall()
    ]

    medications = [
        row_dict(r)
        for r in conn.execute(
            """
            SELECT *
            FROM consultation_medications
            WHERE consultation_id=?
            ORDER BY id
            """,
            (CID,),
        ).fetchall()
    ]

    safety = [
        row_dict(r)
        for r in conn.execute(
            """
            SELECT *
            FROM safety_checks
            WHERE consultation_id=?
            ORDER BY id
            """,
            (CID,),
        ).fetchall()
    ]

    translations = [
        row_dict(r)
        for r in conn.execute(
            """
            SELECT *
            FROM translation_records
            WHERE consultation_id=?
            ORDER BY id
            """,
            (CID,),
        ).fetchall()
    ]

    schedules = [
        row_dict(r)
        for r in conn.execute(
            """
            SELECT *
            FROM medication_schedules
            WHERE consultation_id=?
            ORDER BY id
            """,
            (CID,),
        ).fetchall()
    ]

    events = [
        row_dict(r)
        for r in conn.execute(
            """
            SELECT e.*
            FROM medication_events e
            JOIN medication_schedules s
              ON s.id=e.schedule_id
            WHERE s.consultation_id=?
            ORDER BY e.scheduled_at
            """,
            (CID,),
        ).fetchall()
    ]

    cross_checks = [
        row_dict(r)
        for r in conn.execute(
            """
            SELECT *
            FROM cross_checks
            WHERE consultation_id=?
            ORDER BY id
            """,
            (CID,),
        ).fetchall()
    ]

    audits = [
        row_dict(r)
        for r in conn.execute(
            """
            SELECT *
            FROM audit_logs
            WHERE target_type='consultation'
              AND target_id=?
            ORDER BY id
            """,
            (CID,),
        ).fetchall()
    ]

    manual = json.loads(
        MANUAL.read_text(
            encoding="utf-8"
        )
    )

    actions = {
        a["action"]
        for a in audits
    }

    unresolved = [
        s
        for s in safety
        if s.get("status") in {
            "warning",
            "fail",
        }
        and not bool(
            s.get("resolved")
        )
    ]

    metadata = {}
    try:
        metadata = json.loads(
            c.get("model_metadata")
            or "{}"
        )
    except Exception:
        metadata = {}

    detected = []
    try:
        detected = json.loads(
            c.get("languages_detected")
            or "[]"
        )
    except Exception:
        detected = []

    med = (
        medications[0]
        if medications
        else {}
    )

    translation = (
        translations[-1]
        if translations
        else {}
    )

    checks = []


    def check(
        name,
        passed,
        evidence,
        category,
    ):
        checks.append(
            {
                "name": name,
                "category": category,
                "passed": bool(passed),
                "evidence": evidence,
            }
        )


    # -------------------------------------------------
    # AUTH / CONSENT
    # -------------------------------------------------

    check(
        "Consent recorded",
        "consent.granted"
        in actions,
        "consent.granted audit event",
        "auth_consent",
    )

    check(
        "Consultation created",
        "consultation.created"
        in actions,
        f"consultation_id={CID}",
        "auth_consent",
    )


    # -------------------------------------------------
    # AUDIO / STT
    # -------------------------------------------------

    check(
        "Audio uploaded",
        "consultation.audio_uploaded"
        in actions,
        "consultation.audio_uploaded audit event",
        "stt",
    )

    stt_model = (
        metadata
        .get("stt", {})
        .get("model")
    )

    check(
        "Whisper Medium used",
        stt_model == "medium",
        f"model={stt_model}",
        "stt",
    )

    check(
        "English and Urdu detected",
        (
            "en" in detected
            and "ur" in detected
        ),
        f"languages={detected}",
        "stt",
    )

    check(
        "Code-switch detected",
        bool(
            c.get(
                "code_switched"
            )
        ),
        f"code_switched={c.get('code_switched')}",
        "stt",
    )

    check(
        "No transcript segment remains pending review",
        bool(segments)
        and all(
            not bool(
                s.get(
                    "needs_review"
                )
            )
            for s in segments
        ),
        (
            f"{len(segments)} segments; "
            f"pending="
            f"{sum(bool(s.get('needs_review')) for s in segments)}"
        ),
        "stt",
    )


    # -------------------------------------------------
    # CLINICAL SUMMARY / SAFETY
    # -------------------------------------------------

    summary = (
        c.get(
            "doctor_edited_summary"
        )
        or c.get(
            "patient_summary_en"
        )
        or ""
    )

    check(
        "Clinical patient explanation generated",
        bool(
            summary.strip()
        ),
        "English patient explanation present",
        "clinical_summary",
    )

    check(
        "No unresolved warning/fail safety checks",
        len(unresolved) == 0,
        f"unresolved={len(unresolved)}",
        "safety",
    )

    check(
        "Doctor approval recorded",
        bool(
            c.get(
                "approved_at"
            )
        )
        and (
            "consultation.approved"
            in actions
        ),
        f"approved_at={c.get('approved_at')}",
        "safety",
    )


    # -------------------------------------------------
    # MEDICATION
    # -------------------------------------------------

    frequency = (
        med.get(
            "frequency",
            ""
        )
        or ""
    ).lower()

    duration = (
        med.get(
            "duration",
            ""
        )
        or ""
    ).lower()

    food = (
        med.get(
            "food_instruction",
            ""
        )
        or ""
    ).lower()

    strength = (
        med.get(
            "strength",
            ""
        )
        or ""
    ).lower().replace(
        " ",
        "",
    )

    check(
        "Medication confirmed by doctor",
        bool(
            med
        )
        and bool(
            med.get(
                "doctor_confirmed"
            )
        ),
        (
            f"raw_name="
            f"{med.get('raw_name')}; "
            f"confirmed="
            f"{med.get('doctor_confirmed')}"
        ),
        "medication",
    )

    check(
        "Medication instructions preserved",
        (
            strength
            in {
                "500mg",
                "500milligrams",
            }
            and "twice daily"
            in frequency
            and "2 day"
            in duration
            and "after food"
            in food
        ),
        (
            f"strength={med.get('strength')}; "
            f"frequency={med.get('frequency')}; "
            f"duration={med.get('duration')}; "
            f"food={med.get('food_instruction')}"
        ),
        "medication",
    )


    # -------------------------------------------------
    # TRANSLATION
    # -------------------------------------------------

    manual_translation_verified = (
        "translation.clinician_verified"
        in actions
    )

    check(
        "Urdu translation generated",
        bool(
            translation
        )
        and translation.get(
            "language"
        )
        == "ur"
        and bool(
            translation.get(
                "translated_text"
            )
        ),
        (
            f"language="
            f"{translation.get('language')}"
        ),
        "translation",
    )

    check(
        "Translation numeric preservation passed",
        bool(
            translation.get(
                "numeric_preserved"
            )
        ),
        (
            f"numeric_preserved="
            f"{translation.get('numeric_preserved')}"
        ),
        "translation",
    )

    check(
        "Translation script validation passed",
        bool(
            translation.get(
                "script_valid"
            )
        ),
        (
            f"script_valid="
            f"{translation.get('script_valid')}"
        ),
        "translation",
    )

    check(
        "Translation semantic check or clinician verification passed",
        (
            translation.get(
                "semantic_status"
            )
            == "pass"
            and manual_translation_verified
        ),
        (
            f"semantic_status="
            f"{translation.get('semantic_status')}; "
            f"semantic_score="
            f"{translation.get('semantic_score')}; "
            f"clinician_verified="
            f"{manual_translation_verified}"
        ),
        "translation",
    )


    # -------------------------------------------------
    # TTS / PATIENT DELIVERY
    # -------------------------------------------------

    check(
        "TTS generated",
        bool(
            c.get(
                "tts_backend"
            )
        ),
        f"tts_backend={c.get('tts_backend')}",
        "patient_delivery",
    )

    check(
        "Consultation released",
        c.get(
            "status"
        )
        in {
            "RELEASED",
            "CROSS_CHECKED",
        }
        and bool(
            c.get(
                "released_at"
            )
        )
        and (
            "consultation.released"
            in actions
        ),
        (
            f"status={c.get('status')}; "
            f"released_at={c.get('released_at')}; "
            f"release_audit="
            f"{'consultation.released' in actions}"
        ),
        "patient_delivery",
    )

    check(
        "Patient portal released summary visible",
        manual.get(
            "patient_portal_summary_visible"
        )
        is True,
        "manual patient-side validation",
        "patient_delivery",
    )

    check(
        "Internal clinical data hidden from patient view",
        manual.get(
            "patient_internal_clinical_data_hidden"
        )
        is True,
        "manual patient-side validation",
        "patient_delivery",
    )

    check(
        "Urdu summary audio playback works",
        manual.get(
            "summary_audio_played"
        )
        is True,
        "manual patient-side validation",
        "patient_delivery",
    )


    # -------------------------------------------------
    # SCHEDULER / ALARM
    # -------------------------------------------------

    check(
        "Medication schedule generated",
        len(schedules) == 1,
        f"schedules={len(schedules)}",
        "scheduler_alarm",
    )

    check(
        "Exactly four medication events generated",
        len(events) == 4,
        f"events={len(events)}",
        "scheduler_alarm",
    )

    check(
        "Alarm sound test works",
        manual.get(
            "alarm_test_worked"
        )
        is True,
        "manual patient-side validation",
        "scheduler_alarm",
    )

    check(
        "Voice reminder test works",
        manual.get(
            "voice_test_worked"
        )
        is True,
        "manual patient-side validation",
        "scheduler_alarm",
    )


    # -------------------------------------------------
    # CROSS-CHECK
    # -------------------------------------------------

    completed_cross_checks = [
        x
        for x in cross_checks
        if x.get(
            "request_status"
        )
        == "completed"
    ]

    pending_cross_checks = [
        x
        for x in cross_checks
        if x.get(
            "request_status"
        )
        == "pending"
    ]

    agree_cross_checks = [
        x
        for x in completed_cross_checks
        if x.get(
            "verdict"
        )
        == "agree"
    ]

    check(
        "Second-opinion request completed",
        len(
            completed_cross_checks
        )
        >= 1,
        (
            f"completed="
            f"{len(completed_cross_checks)}"
        ),
        "cross_check",
    )

    check(
        "No pending cross-check remains",
        len(
            pending_cross_checks
        )
        == 0,
        (
            f"pending="
            f"{len(pending_cross_checks)}"
        ),
        "cross_check",
    )

    check(
        "Cross-check verdict persisted",
        len(
            agree_cross_checks
        )
        >= 1,
        (
            f"agree="
            f"{len(agree_cross_checks)}"
        ),
        "cross_check",
    )

    check(
        "Cross-check audit trail recorded",
        (
            "cross_check.requested"
            in actions
            and "cross_check.submitted"
            in actions
        ),
        (
            "request and submission "
            "audit actions present"
        ),
        "cross_check",
    )


    # -------------------------------------------------
    # AUDIT
    # -------------------------------------------------

    required_audit = {
        "consent.granted",
        "consultation.created",
        "consultation.audio_uploaded",
        "consultation.approved",
        "consultation.released",
        "cross_check.requested",
        "cross_check.submitted",
    }

    missing_audit = sorted(
        required_audit - actions
    )

    check(
        "Core end-to-end audit trail complete",
        not missing_audit,
        (
            "missing="
            + (
                ", ".join(
                    missing_audit
                )
                if missing_audit
                else "none"
            )
        ),
        "audit",
    )


    passed = sum(
        1
        for x in checks
        if x["passed"]
    )

    total = len(
        checks
    )

    failed = [
        x
        for x in checks
        if not x["passed"]
    ]


    # Advisory observations are not scored because
    # they are covered by dedicated regression tests
    # or were introduced after consultation 40.
    advisories = [
        {
            "name":
                "Medication terminology concept not demonstrated in consultation 40",
            "detail":
                (
                    "raw_name is preserved safely, "
                    "but canonical_name/concept_id "
                    "were blank in this E2E case. "
                    "Terminology matching is evaluated "
                    "separately in Phase 16E."
                ),
        },
        {
            "name":
                "70% STT clinician-review threshold was added after consultation 40",
            "detail":
                (
                    "Consultation 40 remains the principal "
                    "integrated workflow case. The later "
                    "confidence-gate hardening is validated "
                    "through code regression rather than "
                    "retroactively changing this historical run."
                ),
        },
    ]


    result = {
        "evaluation":
            "MediExplain+ Phase 17 End-to-End",
        "consultation_id":
            CID,
        "evaluated_at":
            datetime.now().isoformat(),
        "passed":
            passed,
        "total":
            total,
        "accuracy_percent":
            round(
                passed
                / total
                * 100,
                1,
            )
            if total
            else 0.0,
        "overall_status":
            (
                "PASS"
                if not failed
                else "FAIL"
            ),
        "checks":
            checks,
        "failed_checks":
            failed,
        "advisories":
            advisories,
    }

    OUT.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


    print()
    print("=" * 76)
    print(
        "MediExplain+ Phase 17 End-to-End Evaluation"
    )
    print("=" * 76)
    print()

    current_category = None

    for item in checks:
        if (
            item["category"]
            != current_category
        ):
            current_category = (
                item["category"]
            )

            print()
            print(
                current_category
                .replace(
                    "_",
                    " ",
                )
                .upper()
            )

        symbol = (
            "PASS"
            if item["passed"]
            else "FAIL"
        )

        print(
            f"{symbol:4}  "
            f"{item['name']}"
        )

        print(
            f"      {item['evidence']}"
        )

    print()
    print("-" * 76)

    print(
        f"Passed:   {passed}/{total}"
    )

    print(
        f"Accuracy: "
        f"{result['accuracy_percent']:.1f}%"
    )

    print(
        f"Status:   "
        f"{result['overall_status']}"
    )

    print()
    print("Advisories:")

    for advisory in advisories:
        print(
            f"  - {advisory['name']}"
        )

    print()
    print(
        f"Saved: {OUT}"
    )

    conn.close()


if __name__ == "__main__":
    main()
