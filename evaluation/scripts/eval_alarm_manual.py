"""Summarise MediExplain+ manual browser alarm evaluation."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

DATA = ROOT / "evaluation" / "data" / "alarm_manual_test.csv"
OUT = ROOT / "evaluation" / "results" / "alarm_manual.json"


with DATA.open(
    encoding="utf-8",
    newline="",
) as fh:
    rows = list(csv.DictReader(fh))


allowed = {
    "PASS",
    "FAIL",
    "NOT_RUN",
}

for row in rows:
    result = (
        row.get("result")
        or "NOT_RUN"
    ).strip().upper()

    if result not in allowed:
        raise ValueError(
            f"{row['test_id']}: invalid result {result!r}. "
            "Use PASS, FAIL or NOT_RUN."
        )

    row["result"] = result


passed = [
    row for row in rows
    if row["result"] == "PASS"
]

failed = [
    row for row in rows
    if row["result"] == "FAIL"
]

pending = [
    row for row in rows
    if row["result"] == "NOT_RUN"
]


categories = defaultdict(
    lambda: {
        "passed": 0,
        "failed": 0,
        "not_run": 0,
        "total": 0,
    }
)

for row in rows:
    item = categories[
        row["category"]
    ]

    item["total"] += 1

    if row["result"] == "PASS":
        item["passed"] += 1
    elif row["result"] == "FAIL":
        item["failed"] += 1
    else:
        item["not_run"] += 1


for item in categories.values():
    completed = (
        item["passed"]
        + item["failed"]
    )

    item["completed"] = completed

    item["accuracy"] = (
        round(
            item["passed"] / completed,
            4,
        )
        if completed
        else None
    )


print()
print("=" * 72)
print("MediExplain+ Browser Alarm Evaluation")
print("=" * 72)
print()

for row in rows:
    print(
        f"{row['result']:<7} "
        f"{row['test_id']:<4} "
        f"{row['requirement']}"
    )


print()
print("-" * 72)
print(f"Passed:   {len(passed)}")
print(f"Failed:   {len(failed)}")
print(f"Not run:  {len(pending)}")
print(f"Total:    {len(rows)}")


if pending:
    print()
    print(
        "Alarm evaluation is not complete. "
        "No final alarm result has been written."
    )
    print()
    print(
        "Fill PASS or FAIL in:"
    )
    print(
        "  evaluation/data/alarm_manual_test.csv"
    )

else:
    accuracy = (
        len(passed)
        / len(rows)
        if rows
        else 0
    )

    result = {
        "evaluation":
            "browser_medication_alarm",

        "passed":
            len(passed),

        "failed":
            len(failed),

        "total":
            len(rows),

        "accuracy":
            round(
                accuracy,
                4,
            ),

        "per_category":
            dict(categories),

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

    print()
    print(
        f"Accuracy: {accuracy * 100:.1f}%"
    )

    if failed:
        print()
        print("Failures:")
        for row in failed:
            print(
                f"  {row['test_id']}: "
                f"{row['requirement']}"
            )

    print()
    print("Saved:")
    print(
        f"  {OUT.relative_to(ROOT)}"
    )
