"""Live MediExplain+ doctor cross-check workflow evaluation.

Tests the deployed API, authorization boundaries, persistence and audit trail.

Prerequisites:
- backend running on http://127.0.0.1:8000
- demo users seeded
"""

from __future__ import annotations

import json
import sqlite3
import sys

from pathlib import Path

import httpx


BASE = "http://127.0.0.1:8000"

ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

DB = (
    ROOT
    / "backend"
    / "data"
    / "mediexplain.db"
)

OUT = (
    ROOT
    / "evaluation"
    / "results"
    / "cross_check.json"
)

OUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)


DOCTOR = "doctor@demo.com"
ASSIGNED_REVIEWER = "doctor2@demo.com"
OTHER_REVIEWER = "reviewer@demo.com"
PATIENT = "patient.ur@demo.com"

PASSWORD = "demo1234"


results = []


# ============================================================
# HELPERS
# ============================================================

class Tokens:
    def __init__(self):
        self.cache = {}

    def headers(
        self,
        email,
    ):
        if email not in self.cache:

            response = httpx.post(
                BASE + "/api/auth/login",
                data={
                    "username": email,
                    "password": PASSWORD,
                },
                timeout=10,
            )

            response.raise_for_status()

            token = (
                response
                .json()[
                    "access_token"
                ]
            )

            self.cache[
                email
            ] = {
                "Authorization":
                    "Bearer " + token
            }

        return self.cache[
            email
        ]


TOKENS = Tokens()


def check(
    name,
    condition,
    detail="",
    category="workflow",
):
    passed = bool(
        condition
    )

    results.append(
        {
            "name": name,
            "category": category,
            "pass": passed,
            "detail": detail,
        }
    )

    print(
        ("✓" if passed else "✗"),
        name,
        detail,
    )


def get_user_id(
    email,
):
    con = sqlite3.connect(
        DB
    )

    try:
        row = con.execute(
            "SELECT id FROM users WHERE email=?",
            (email,),
        ).fetchone()

    finally:
        con.close()

    if not row:
        raise RuntimeError(
            f"Demo user missing: {email}"
        )

    return int(
        row[0]
    )


# ============================================================
# BACKEND HEALTH
# ============================================================

try:
    httpx.get(
        BASE + "/api/health",
        timeout=3,
    ).raise_for_status()

except Exception as exc:
    print(
        "Backend unavailable:",
        exc,
    )

    sys.exit(2)


# ============================================================
# LOGIN / IDS
# ============================================================

for email in (
    DOCTOR,
    ASSIGNED_REVIEWER,
    OTHER_REVIEWER,
    PATIENT,
):
    TOKENS.headers(
        email
    )


doctor_id = get_user_id(
    DOCTOR
)

assigned_reviewer_id = (
    get_user_id(
        ASSIGNED_REVIEWER
    )
)

other_reviewer_id = (
    get_user_id(
        OTHER_REVIEWER
    )
)

patient_id = get_user_id(
    PATIENT
)


# ============================================================
# TEMPORARY CONSULTATION
# ============================================================

response = httpx.post(
    BASE + "/api/consultations/",
    headers=TOKENS.headers(
        DOCTOR
    ),
    json={
        "patient_id":
            patient_id,

        "doctor_consent":
            True,

        "patient_consent":
            True,

        "patient_language":
            "ur",

        "consent_method":
            "verbal",
    },
    timeout=10,
)

response.raise_for_status()

consultation_id = (
    response.json()[
        "id"
    ]
)


print()
print(
    "=" * 76
)
print(
    "MediExplain+ Cross-Check Workflow Evaluation"
)
print(
    "=" * 76
)
print()


try:

    # ========================================================
    # 1. TREATING DOCTOR CANNOT REVIEW OWN CASE
    # ========================================================

    response = httpx.post(
        BASE
        + "/api/cross-check/request",
        headers=TOKENS.headers(
            DOCTOR
        ),
        json={
            "consultation_id":
                consultation_id,

            "reviewer_id":
                doctor_id,

            "reason":
                "Cross-check evaluation",
        },
        timeout=10,
    )

    check(
        "Treating doctor cannot assign self as reviewer",
        response.status_code == 400,
        str(response.status_code),
        "authorization",
    )


    # ========================================================
    # 2. OWNER CREATES VALID ASSIGNMENT
    # ========================================================

    response = httpx.post(
        BASE
        + "/api/cross-check/request",
        headers=TOKENS.headers(
            DOCTOR
        ),
        json={
            "consultation_id":
                consultation_id,

            "reviewer_id":
                assigned_reviewer_id,

            "reason":
                "Independent clinical review",
        },
        timeout=10,
    )

    check(
        "Treating doctor can create explicit reviewer assignment",
        response.status_code == 201,
        str(response.status_code),
    )

    if response.status_code != 201:
        raise RuntimeError(
            "Could not create cross-check assignment."
        )

    cross_check = (
        response.json()
    )

    cross_check_id = (
        cross_check[
            "id"
        ]
    )

    check(
        "New cross-check starts pending",
        cross_check.get(
            "request_status"
        ) == "pending",
        str(
            cross_check.get(
                "request_status"
            )
        ),
    )


    # ========================================================
    # 3. DUPLICATE ACTIVE ASSIGNMENT REJECTED
    # ========================================================

    duplicate = httpx.post(
        BASE
        + "/api/cross-check/request",
        headers=TOKENS.headers(
            DOCTOR
        ),
        json={
            "consultation_id":
                consultation_id,

            "reviewer_id":
                assigned_reviewer_id,

            "reason":
                "Duplicate assignment attempt",
        },
        timeout=10,
    )

    check(
        "Duplicate active reviewer assignment rejected",
        duplicate.status_code == 409,
        str(
            duplicate.status_code
        ),
        "safety",
    )


    # ========================================================
    # 4. UNASSIGNED REVIEWER CANNOT ACCESS CASE
    # ========================================================

    response = httpx.get(
        (
            BASE
            + f"/api/consultations/{consultation_id}"
        ),
        headers=TOKENS.headers(
            OTHER_REVIEWER
        ),
        timeout=10,
    )

    check(
        "Unassigned reviewer cannot access consultation",
        response.status_code == 403,
        str(
            response.status_code
        ),
        "authorization",
    )


    # ========================================================
    # 5. ASSIGNED REVIEWER CAN ACCESS CASE
    # ========================================================

    response = httpx.get(
        (
            BASE
            + f"/api/consultations/{consultation_id}"
        ),
        headers=TOKENS.headers(
            ASSIGNED_REVIEWER
        ),
        timeout=10,
    )

    check(
        "Assigned reviewer can access consultation",
        response.status_code == 200,
        str(
            response.status_code
        ),
        "authorization",
    )


    # ========================================================
    # 6. UNASSIGNED REVIEWER CANNOT SUBMIT
    # ========================================================

    response = httpx.post(
        (
            BASE
            + f"/api/cross-check/{cross_check_id}/submit"
        ),
        headers=TOKENS.headers(
            OTHER_REVIEWER
        ),
        json={
            "verdict":
                "agree",

            "comments":
                "Unauthorized submission attempt",
        },
        timeout=10,
    )

    check(
        "Unassigned reviewer cannot submit review",
        response.status_code == 403,
        str(
            response.status_code
        ),
        "authorization",
    )


    # ========================================================
    # 7. ASSIGNED REVIEWER SEES PENDING ASSIGNMENT
    # ========================================================

    response = httpx.get(
        BASE
        + "/api/cross-check/pending",
        headers=TOKENS.headers(
            ASSIGNED_REVIEWER
        ),
        timeout=10,
    )

    pending_rows = (
        response.json()
        if response.status_code
        == 200
        else []
    )

    pending_ids = {
        row.get("id")
        for row
        in pending_rows
    }

    check(
        "Assigned review appears in reviewer pending list",
        (
            response.status_code == 200
            and cross_check_id
            in pending_ids
        ),
        (
            f"status={response.status_code}, "
            f"found={cross_check_id in pending_ids}"
        ),
    )


    # ========================================================
    # 8. ASSIGNED REVIEWER SUBMITS
    # ========================================================

    comments = (
        "Clinical information reviewed. "
        "No discrepancy identified."
    )

    response = httpx.post(
        (
            BASE
            + f"/api/cross-check/{cross_check_id}/submit"
        ),
        headers=TOKENS.headers(
            ASSIGNED_REVIEWER
        ),
        json={
            "verdict":
                "agree",

            "comments":
                comments,
        },
        timeout=10,
    )

    submitted = (
        response.json()
        if response.status_code
        == 200
        else {}
    )

    check(
        "Assigned reviewer can submit cross-check",
        response.status_code == 200,
        str(
            response.status_code
        ),
    )

    check(
        "Submitted review becomes completed",
        submitted.get(
            "request_status"
        ) == "completed",
        str(
            submitted.get(
                "request_status"
            )
        ),
    )

    check(
        "Submitted verdict persists in API response",
        submitted.get(
            "verdict"
        ) == "agree",
        str(
            submitted.get(
                "verdict"
            )
        ),
    )

    check(
        "Submitted comments persist in API response",
        submitted.get(
            "comments"
        ) == comments,
        str(
            submitted.get(
                "comments"
            )
        ),
    )

    check(
        "Completed review records completion time",
        bool(
            submitted.get(
                "completed_at"
            )
        ),
        str(
            submitted.get(
                "completed_at"
            )
        ),
    )


    # ========================================================
    # 9. COMPLETED REVIEW CANNOT BE SUBMITTED AGAIN
    # ========================================================

    response = httpx.post(
        (
            BASE
            + f"/api/cross-check/{cross_check_id}/submit"
        ),
        headers=TOKENS.headers(
            ASSIGNED_REVIEWER
        ),
        json={
            "verdict":
                "disagree",

            "comments":
                "Second submission should be rejected",
        },
        timeout=10,
    )

    check(
        "Completed review cannot be submitted twice",
        response.status_code == 409,
        str(
            response.status_code
        ),
        "safety",
    )


    # ========================================================
    # 10. COMPLETED REVIEW DISAPPEARS FROM PENDING
    # ========================================================

    response = httpx.get(
        BASE
        + "/api/cross-check/pending",
        headers=TOKENS.headers(
            ASSIGNED_REVIEWER
        ),
        timeout=10,
    )

    pending_rows = (
        response.json()
        if response.status_code
        == 200
        else []
    )

    pending_ids = {
        row.get("id")
        for row
        in pending_rows
    }

    check(
        "Completed review removed from pending list",
        (
            response.status_code == 200
            and cross_check_id
            not in pending_ids
        ),
        (
            f"status={response.status_code}, "
            f"still_pending={cross_check_id in pending_ids}"
        ),
    )


    # ========================================================
    # 11. OWNER CAN SEE COMPLETED OUTCOME
    # ========================================================

    response = httpx.get(
        (
            BASE
            + "/api/cross-check/"
            + f"for-consultation/{consultation_id}"
        ),
        headers=TOKENS.headers(
            DOCTOR
        ),
        timeout=10,
    )

    owner_rows = (
        response.json()
        if response.status_code
        == 200
        else []
    )

    owner_result = next(
        (
            row
            for row
            in owner_rows
            if row.get(
                "id"
            )
            == cross_check_id
        ),
        None,
    )

    check(
        "Treating doctor can view completed review outcome",
        (
            response.status_code == 200
            and owner_result is not None
        ),
        str(
            response.status_code
        ),
    )

    check(
        "Completed outcome preserves reviewer verdict",
        (
            owner_result is not None
            and owner_result.get(
                "verdict"
            )
            == "agree"
        ),
        str(
            (
                owner_result
                or {}
            ).get(
                "verdict"
            )
        ),
    )


    # ========================================================
    # 12. UNASSIGNED REVIEWER STILL CANNOT SEE OUTCOME
    # ========================================================

    response = httpx.get(
        (
            BASE
            + "/api/cross-check/"
            + f"for-consultation/{consultation_id}"
        ),
        headers=TOKENS.headers(
            OTHER_REVIEWER
        ),
        timeout=10,
    )

    check(
        "Unassigned reviewer cannot read cross-check outcome",
        response.status_code == 403,
        str(
            response.status_code
        ),
        "authorization",
    )


    # ========================================================
    # 13. AUDIT TRAIL
    # ========================================================

    con = sqlite3.connect(
        DB
    )

    try:
        rows = con.execute(
            """
            SELECT action, details
            FROM audit_logs
            WHERE target_type='consultation'
              AND target_id=?
              AND action IN (
                  'cross_check.requested',
                  'cross_check.submitted'
              )
            ORDER BY id
            """,
            (
                consultation_id,
            ),
        ).fetchall()

    finally:
        con.close()


    actions = [
        row[0]
        for row
        in rows
    ]

    check(
        "Cross-check request creates audit record",
        "cross_check.requested"
        in actions,
        str(
            actions
        ),
        "audit",
    )

    check(
        "Cross-check submission creates audit record",
        "cross_check.submitted"
        in actions,
        str(
            actions
        ),
        "audit",
    )


    # Audit details should not contain full clinical content.
    audit_text = " ".join(
        str(
            row[1]
            or ""
        )
        for row
        in rows
    ).lower()

    forbidden_terms = (
        "raw_transcript",
        "patient_summary",
        "clinical_note",
        "prescription_image",
        "audio_path",
    )

    minimal_audit = not any(
        term in audit_text
        for term
        in forbidden_terms
    )

    check(
        "Cross-check audit records avoid full clinical payloads",
        minimal_audit,
        "",
        "audit",
    )


finally:

    # ========================================================
    # CLEANUP
    # ========================================================

    cleanup = httpx.delete(
        (
            BASE
            + f"/api/consultations/{consultation_id}"
        ),
        headers=TOKENS.headers(
            DOCTOR
        ),
        timeout=10,
    )

    check(
        "Temporary evaluation consultation cleaned up",
        cleanup.status_code
        in {
            204,
            404,
        },
        str(
            cleanup.status_code
        ),
        "cleanup",
    )


# ============================================================
# SUMMARY
# ============================================================

passed = sum(
    item["pass"]
    for item
    in results
)

total = len(
    results
)


categories = {}

for row in results:

    category = (
        row["category"]
    )

    categories.setdefault(
        category,
        {
            "passed": 0,
            "total": 0,
        },
    )

    categories[
        category
    ][
        "total"
    ] += 1

    categories[
        category
    ][
        "passed"
    ] += int(
        row[
            "pass"
        ]
    )


for category, values in (
    categories.items()
):

    values[
        "accuracy"
    ] = round(
        values[
            "passed"
        ]
        / values[
            "total"
        ],
        4,
    )


result = {
    "evaluation":
        "doctor_cross_check_workflow",

    "passed":
        passed,

    "total":
        total,

    "accuracy":
        round(
            passed / total,
            4,
        ),

    "all_pass":
        passed == total,

    "per_category":
        categories,

    "checks":
        results,
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
print(
    "-" * 76
)

print(
    f"Passed:   {passed}/{total}"
)

print(
    f"Accuracy: "
    f"{passed / total * 100:.1f}%"
)

print()
print(
    "Per category:"
)

for category, values in (
    categories.items()
):

    print(
        f"  {category:<16}"
        f"{values['passed']}/"
        f"{values['total']} "
        f"({values['accuracy'] * 100:.1f}%)"
    )


print()
print(
    "Saved:"
)

print(
    f"  {OUT.relative_to(ROOT)}"
)


sys.exit(
    0
    if passed == total
    else 1
)
