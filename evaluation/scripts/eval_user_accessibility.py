"""Summarise real MediExplain+ user and accessibility testing."""

from __future__ import annotations

import csv
import json
import statistics

from collections import defaultdict
from pathlib import Path


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

DATA = (
    ROOT
    / "evaluation"
    / "data"
    / "user_accessibility_ratings.csv"
)

OUT = (
    ROOT
    / "evaluation"
    / "results"
    / "user_accessibility.json"
)

OUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)


TASK_COLUMNS = [
    "task_1_complete",
    "task_2_complete",
    "task_3_complete",
    "task_4_complete",
    "task_5_complete",
]


RATING_COLUMNS = [
    "ease_of_use",
    "information_clarity",
    "language_clarity",
    "medication_understanding",
    "voice_usefulness",
    "accessibility",
    "trust_in_system",
    "overall_satisfaction",
]


def yes_value(value):
    value = (
        value
        or ""
    ).strip().lower()

    if value in {
        "yes",
        "y",
        "true",
        "1",
        "pass",
    }:
        return 1

    if value in {
        "no",
        "n",
        "false",
        "0",
        "fail",
    }:
        return 0

    return None


def rating_value(value):
    text = (
        value
        or ""
    ).strip()

    if not text:
        return None

    if text.lower() in {
        "na",
        "n/a",
        "not applicable",
    }:
        return None

    try:
        score = float(
            text
        )
    except ValueError:
        return None

    if not (
        1 <= score <= 5
    ):
        return None

    return score


def mean(values):
    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return None

    return round(
        statistics.mean(
            values
        ),
        3,
    )


with DATA.open(
    encoding="utf-8",
    newline="",
) as handle:

    rows = list(
        csv.DictReader(
            handle
        )
    )


# Remove entirely empty rows.
rows = [
    row
    for row in rows
    if any(
        (
            value
            or ""
        ).strip()
        for value
        in row.values()
    )
]


print()
print("=" * 76)
print("MediExplain+ User + Accessibility Evaluation")
print("=" * 76)
print()


if not rows:

    print(
        "User evaluation infrastructure is ready."
    )

    print(
        "No real participant results have been entered yet."
    )

    print()
    print(
        "Enter anonymised results into:"
    )

    print(
        "  evaluation/data/user_accessibility_ratings.csv"
    )

    raise SystemExit(0)


# ============================================================
# PARTICIPANT VALIDATION
# ============================================================

participant_ids = [
    (
        row.get(
            "participant_id"
        )
        or ""
    ).strip()
    for row in rows
]


missing_ids = [
    index + 1
    for index, pid
    in enumerate(
        participant_ids
    )
    if not pid
]


if missing_ids:
    raise ValueError(
        "Missing participant IDs in row(s): "
        + ", ".join(
            map(
                str,
                missing_ids,
            )
        )
    )


if (
    len(
        set(
            participant_ids
        )
    )
    != len(
        participant_ids
    )
):
    raise ValueError(
        "Participant IDs must be unique."
    )


# ============================================================
# PER-ROLE ANALYSIS
# ============================================================

groups = defaultdict(
    list
)

for row in rows:
    role = (
        row.get(
            "role"
        )
        or "unknown"
    ).strip().lower()

    groups[
        role
    ].append(
        row
    )


def analyse_group(
    group_rows,
):

    task_values = []

    for row in group_rows:

        for column in (
            TASK_COLUMNS
        ):
            value = yes_value(
                row.get(
                    column
                )
            )

            if value is not None:
                task_values.append(
                    value
                )


    ratings = {}

    for column in (
        RATING_COLUMNS
    ):

        values = [
            rating_value(
                row.get(
                    column
                )
            )
            for row in group_rows
        ]

        ratings[
            column
        ] = {
            "n":
                sum(
                    value
                    is not None
                    for value
                    in values
                ),

            "mean":
                mean(
                    values
                ),
        }


    reuse = [
        yes_value(
            row.get(
                "would_use_again"
            )
        )
        for row
        in group_rows
    ]

    reuse = [
        value
        for value in reuse
        if value is not None
    ]


    return {
        "participants":
            len(
                group_rows
            ),

        "task_completion": {
            "completed":
                sum(
                    task_values
                ),

            "attempted":
                len(
                    task_values
                ),

            "rate":
                round(
                    sum(
                        task_values
                    )
                    / len(
                        task_values
                    ),
                    4,
                )
                if task_values
                else None,
        },

        "ratings":
            ratings,

        "would_use_again": {
            "yes":
                sum(
                    reuse
                ),

            "responses":
                len(
                    reuse
                ),

            "rate":
                round(
                    sum(
                        reuse
                    )
                    / len(
                        reuse
                    ),
                    4,
                )
                if reuse
                else None,
        },
    }


per_role = {
    role:
        analyse_group(
            group_rows
        )
    for role, group_rows
    in groups.items()
}


overall = (
    analyse_group(
        rows
    )
)


# ============================================================
# LANGUAGE DISTRIBUTION
# ============================================================

languages = defaultdict(
    int
)

for row in rows:
    language = (
        row.get(
            "preferred_language"
        )
        or "unspecified"
    ).strip()

    languages[
        language
    ] += 1


result = {
    "evaluation":
        "user_accessibility",

    "participants":
        len(
            rows
        ),

    "roles": {
        role:
            len(
                group_rows
            )
        for role, group_rows
        in groups.items()
    },

    "languages":
        dict(
            languages
        ),

    "overall":
        overall,

    "per_role":
        per_role,
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
# CONSOLE SUMMARY
# ============================================================

print(
    f"Participants: {len(rows)}"
)

print()


task_rate = (
    overall[
        "task_completion"
    ][
        "rate"
    ]
)

if task_rate is not None:
    print(
        "Overall task completion: "
        f"{task_rate * 100:.1f}%"
    )


print()

for role, metrics in (
    per_role.items()
):

    print(
        role.upper()
    )

    print(
        "-" * 40
    )

    print(
        "Participants: "
        f"{metrics['participants']}"
    )

    rate = (
        metrics[
            "task_completion"
        ][
            "rate"
        ]
    )

    if rate is not None:

        print(
            "Task completion: "
            f"{rate * 100:.1f}%"
        )

    print(
        "Ratings:"
    )

    for key, value in (
        metrics[
            "ratings"
        ].items()
    ):

        if value[
            "mean"
        ] is not None:

            label = (
                key.replace(
                    "_",
                    " "
                )
                .title()
            )

            print(
                f"  {label:<27}"
                f"{value['mean']:.2f}/5 "
                f"(n={value['n']})"
            )

    reuse = (
        metrics[
            "would_use_again"
        ][
            "rate"
        ]
    )

    if reuse is not None:

        print(
            "Would use again: "
            f"{reuse * 100:.1f}%"
        )

    print()


print(
    "Saved:"
)

print(
    f"  {OUT.relative_to(ROOT)}"
)
