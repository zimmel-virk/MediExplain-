"""MediExplain+ deterministic medication scheduling evaluation."""

from __future__ import annotations

import json
import sys

from datetime import date
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

sys.path.insert(
    0,
    str(
        ROOT
        / "backend"
    ),
)

from app.services.scheduler import (
    build_events,
    parse_duration,
    parse_frequency,
)


OUT = (
    ROOT
    / "evaluation"
    / "results"
    / "scheduler.json"
)

OUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)


START = date(
    2026,
    8,
    10,
)


# ============================================================
# SUCCESSFUL SCHEDULE CASES
# ============================================================

CASES = [
    # English daily counts
    {
        "id": "en_once",
        "language": "English",
        "frequency": "once daily",
        "duration": "7 days",
        "expected_events": 7,
        "expected_daily_times": ["09:00"],
    },
    {
        "id": "en_twice",
        "language": "English",
        "frequency": "twice daily",
        "duration": "7 days",
        "expected_events": 14,
        "expected_daily_times": ["09:00", "21:00"],
    },
    {
        "id": "en_three",
        "language": "English",
        "frequency": "three times a day",
        "duration": "5 days",
        "expected_events": 15,
        "expected_daily_times": ["08:00", "14:00", "20:00"],
    },
    {
        "id": "en_four",
        "language": "English",
        "frequency": "four times per day",
        "duration": "3 days",
        "expected_events": 12,
        "expected_daily_times": ["08:00", "12:00", "16:00", "20:00"],
    },

    # English interval schedules
    {
        "id": "every_12",
        "language": "English",
        "frequency": "every 12 hours",
        "duration": "2 days",
        "expected_events": 4,
    },
    {
        "id": "every_8",
        "language": "English",
        "frequency": "every 8 hours",
        "duration": "2 days",
        "expected_events": 6,
    },
    {
        "id": "every_6",
        "language": "English",
        "frequency": "every 6 hours",
        "duration": "1 day",
        "expected_events": 4,
    },
    {
        "id": "every_4",
        "language": "English",
        "frequency": "every 4 hours",
        "duration": "1 day",
        "expected_events": 6,
    },
    {
        "id": "q8h",
        "language": "Clinical abbreviation",
        "frequency": "q8h",
        "duration": "1 day",
        "expected_events": 3,
    },

    # Named times
    {
        "id": "morning_night",
        "language": "English",
        "frequency": "morning and night",
        "duration": "7 days",
        "expected_events": 14,
        "expected_daily_times": ["08:00", "21:00"],
    },

    # Urdu
    {
        "id": "ur_once",
        "language": "Urdu",
        "frequency": "دن میں ایک دفعہ",
        "duration": "3 دن",
        "expected_events": 3,
        "expected_daily_times": ["09:00"],
    },
    {
        "id": "ur_twice",
        "language": "Urdu",
        "frequency": "دن میں دو دفعہ",
        "duration": "7 دن",
        "expected_events": 14,
        "expected_daily_times": ["09:00", "21:00"],
    },
    {
        "id": "ur_three",
        "language": "Urdu",
        "frequency": "روزانہ تین بار",
        "duration": "2 دن",
        "expected_events": 6,
        "expected_daily_times": ["08:00", "14:00", "20:00"],
    },
    {
        "id": "ur_four",
        "language": "Urdu",
        "frequency": "دن میں چار بار",
        "duration": "2 دن",
        "expected_events": 8,
        "expected_daily_times": ["08:00", "12:00", "16:00", "20:00"],
    },
    {
        "id": "ur_named",
        "language": "Urdu",
        "frequency": "صبح اور رات",
        "duration": "2 دن",
        "expected_events": 4,
        "expected_daily_times": ["08:00", "21:00"],
    },
    {
        "id": "ur_interval",
        "language": "Urdu",
        "frequency": "ہر 8 گھنٹے",
        "duration": "2 دن",
        "expected_events": 6,
    },

    # Punjabi Shahmukhi
    {
        "id": "pa_once",
        "language": "Punjabi Shahmukhi",
        "frequency": "دن وچ اک واری",
        "duration": "2 دن",
        "expected_events": 2,
        "expected_daily_times": ["09:00"],
    },
    {
        "id": "pa_twice",
        "language": "Punjabi Shahmukhi",
        "frequency": "دن وچ دو واری",
        "duration": "2 دن",
        "expected_events": 4,
        "expected_daily_times": ["09:00", "21:00"],
    },

    # Mixed language
    {
        "id": "mixed_twice",
        "language": "Mixed",
        "frequency": "twice daily - دن میں دو دفعہ",
        "duration": "5 days",
        "expected_events": 10,
        "expected_daily_times": ["09:00", "21:00"],
    },

    # Longer duration
    {
        "id": "two_weeks",
        "language": "English",
        "frequency": "once daily",
        "duration": "2 weeks",
        "expected_events": 14,
        "expected_daily_times": ["09:00"],
    },
    {
        "id": "ur_two_weeks",
        "language": "Urdu",
        "frequency": "دن میں ایک بار",
        "duration": "2 ہفتے",
        "expected_events": 14,
        "expected_daily_times": ["09:00"],
    },
]


# ============================================================
# SAFETY / REJECTION CASES
# ============================================================

SAFETY_CASES = [
    {
        "id": "missing_duration",
        "frequency": "twice daily",
        "duration": None,
        "kind": "error",
    },
    {
        "id": "unsupported_interval",
        "frequency": "every 5 hours",
        "duration": "2 days",
        "kind": "error",
    },
    {
        "id": "unknown_instruction",
        "frequency": "after food",
        "duration": "5 days",
        "kind": "error",
    },
    {
        "id": "missing_frequency",
        "frequency": "",
        "duration": "5 days",
        "kind": "error",
    },
    {
        "id": "prn_en",
        "frequency": "as needed",
        "duration": None,
        "kind": "prn",
    },
    {
        "id": "prn_abbreviation",
        "frequency": "PRN",
        "duration": None,
        "kind": "prn",
    },
    {
        "id": "prn_ur",
        "frequency": "ضرورت کے مطابق",
        "duration": None,
        "kind": "prn",
    },
]


# ============================================================
# RUN SUCCESS CASES
# ============================================================

rows = []


for case in CASES:

    end = parse_duration(
        case["duration"],
        START,
    )

    events, error = (
        build_events(
            case["frequency"],
            START,
            end,
            "Asia/Karachi",
        )
    )

    actual_times = sorted(
        {
            event.strftime(
                "%H:%M"
            )
            for event in events
        }
    )

    expected_times = sorted(
        case.get(
            "expected_daily_times",
            [],
        )
    )

    count_ok = (
        len(events)
        == case[
            "expected_events"
        ]
    )

    time_ok = (
        True
        if not expected_times
        else (
            actual_times
            == expected_times
        )
    )

    ordered_ok = (
        events
        == sorted(events)
    )

    unique_ok = (
        len(events)
        == len(
            set(events)
        )
    )

    passed = (
        error is None
        and count_ok
        and time_ok
        and ordered_ok
        and unique_ok
    )

    rows.append(
        {
            **case,
            "actual_events":
                len(events),

            "actual_daily_times":
                actual_times,

            "error":
                error,

            "count_pass":
                count_ok,

            "time_pass":
                time_ok,

            "ordered_pass":
                ordered_ok,

            "unique_pass":
                unique_ok,

            "pass":
                passed,
        }
    )


# ============================================================
# RUN SAFETY CASES
# ============================================================

for case in SAFETY_CASES:

    end = (
        parse_duration(
            case[
                "duration"
            ],
            START,
        )
        if case[
            "duration"
        ]
        else None
    )

    events, error = (
        build_events(
            case[
                "frequency"
            ],
            START,
            end,
            "Asia/Karachi",
        )
    )

    if (
        case[
            "kind"
        ]
        == "prn"
    ):

        passed = (
            events == []
            and error is None
        )

    else:

        passed = (
            events == []
            and bool(error)
        )

    rows.append(
        {
            **case,
            "expected_events":
                0,

            "actual_events":
                len(events),

            "error":
                error,

            "pass":
                passed,
        }
    )


# ============================================================
# AGGREGATE
# ============================================================

passed = sum(
    bool(
        row[
            "pass"
        ]
    )
    for row in rows
)

total = len(
    rows
)


language_results = {}

for row in rows:

    language = row.get(
        "language"
    )

    if not language:
        continue

    language_results.setdefault(
        language,
        {
            "passed": 0,
            "total": 0,
        },
    )

    language_results[
        language
    ][
        "total"
    ] += 1

    language_results[
        language
    ][
        "passed"
    ] += int(
        row[
            "pass"
        ]
    )


for language, metrics in (
    language_results.items()
):

    metrics[
        "accuracy"
    ] = round(
        metrics[
            "passed"
        ]
        / metrics[
            "total"
        ],
        4,
    )


result = {
    "evaluation":
        "deterministic_medication_scheduler",

    "passed":
        passed,

    "total":
        total,

    "accuracy":
        round(
            passed
            / total,
            4,
        ),

    "per_language":
        language_results,

    "cases":
        rows,
}


OUT.write_text(
    json.dumps(
        result,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)


# ============================================================
# CONSOLE
# ============================================================

print()
print(
    "=" * 76
)

print(
    "MediExplain+ Scheduler Evaluation"
)

print(
    "=" * 76
)

print()

for row in rows:

    status = (
        "PASS"
        if row[
            "pass"
        ]
        else "FAIL"
    )

    print(
        f"{status:<4}  "
        f"{row['id']:<23}"
        f"{row['frequency']!r}"
    )

    if not row[
        "pass"
    ]:

        print(
            f"      expected events: "
            f"{row.get('expected_events')}"
        )

        print(
            f"      actual events:   "
            f"{row.get('actual_events')}"
        )

        print(
            f"      error:           "
            f"{row.get('error')}"
        )


print()
print(
    "-" * 76
)

print(
    f"Passed:    {passed}/{total}"
)

print(
    f"Accuracy:  "
    f"{passed / total * 100:.1f}%"
)

print()
print(
    "Per language:"
)


for language, metrics in (
    language_results.items()
):

    print(
        f"  {language:<21}"
        f"{metrics['passed']}/"
        f"{metrics['total']} "
        f"({metrics['accuracy'] * 100:.1f}%)"
    )


print()
print(
    "Saved:"
)

print(
    f"  {OUT.relative_to(ROOT)}"
)
