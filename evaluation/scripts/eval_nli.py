"""
MediExplain+ Final NLI Safety Evaluation

Evaluates the ACTUAL deployed NLI decision logic from:

    app.services.nli.check_pair()

Gold labels:
    entailment
    neutral
    contradiction

Application decisions:
    entailed
    unsupported
    contradiction

Safety interpretation:
    Gold entailment               -> supported
    Gold neutral/contradiction    -> unsafe / should be flagged

Most important safety failure:
    gold neutral/contradiction
    predicted entailed
    = safety false negative

Input:
    evaluation/data/nli_test_set.json

Output:
    evaluation/results/nli.json
    evaluation/results/nli_detailed.csv
"""

from __future__ import annotations

import csv
import json
import statistics
import sys

from collections import defaultdict
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

sys.path.insert(
    0,
    str(ROOT / "backend"),
)

from app.services.nli import check_pair


DATA = (
    ROOT
    / "evaluation"
    / "data"
    / "nli_test_set.json"
)

RESULTS_DIR = (
    ROOT
    / "evaluation"
    / "results"
)

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

JSON_OUT = (
    RESULTS_DIR
    / "nli.json"
)

CSV_OUT = (
    RESULTS_DIR
    / "nli_detailed.csv"
)


# ============================================================
# LABELS
# ============================================================

GOLD_LABELS = (
    "entailment",
    "neutral",
    "contradiction",
)

DEPLOYED_LABELS = (
    "entailed",
    "unsupported",
    "contradiction",
)


def deployed_to_eval_label(
    label: str,
) -> str:

    mapping = {
        "entailed":
            "entailment",

        "unsupported":
            "neutral",

        "contradiction":
            "contradiction",
    }

    return mapping.get(
        label,
        "unavailable",
    )


def gold_is_unsafe(
    label: str,
) -> bool:

    return label in {
        "neutral",
        "contradiction",
    }


def deployment_flagged(
    label: str,
) -> bool:

    return label in {
        "unsupported",
        "contradiction",
    }


# ============================================================
# HELPERS
# ============================================================

def safe_div(
    numerator: int,
    denominator: int,
) -> float:

    if denominator == 0:
        return 0.0

    return (
        numerator
        / denominator
    )


def round4(
    value: float | None,
):

    if value is None:
        return None

    return round(
        value,
        4,
    )


def mean_or_none(
    values,
):

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
        4,
    )


# ============================================================
# LOAD DATA
# ============================================================

if not DATA.exists():

    DATA.write_text(
        json.dumps(
            {
                "_comment":
                    (
                        "Add clinician-reviewed "
                        "NLI evidence/statement pairs."
                    ),
                "cases": [],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"Created {DATA}"
    )

    sys.exit(0)


payload = json.loads(
    DATA.read_text(
        encoding="utf-8",
    )
)

cases = payload.get(
    "cases",
    [],
)


if not cases:

    print()
    print(
        "=" * 72
    )

    print(
        "MediExplain+ NLI Safety Evaluation"
    )

    print(
        "=" * 72
    )

    print()
    print(
        "NLI evaluation infrastructure is ready."
    )

    print(
        "No clinician-reviewed labelled cases "
        "have been entered yet."
    )

    print()
    print(
        "Enter cases into:"
    )

    print(
        f"  {DATA.relative_to(ROOT)}"
    )

    print()

    sys.exit(0)


# ============================================================
# VALIDATE DATA
# ============================================================

required_fields = {
    "id",
    "evidence",
    "statement",
    "label",
}


for index, case in enumerate(
    cases,
    start=1,
):

    missing = (
        required_fields
        - set(case.keys())
    )

    if missing:

        raise ValueError(
            f"Case {index} is missing: "
            f"{sorted(missing)}"
        )


    if (
        case["label"]
        not in GOLD_LABELS
    ):

        raise ValueError(
            f"Case {case['id']}: "
            "label must be one of "
            "entailment, neutral, contradiction."
        )


# ============================================================
# RUN NLI
# ============================================================

print()
print(
    "=" * 72
)

print(
    "MediExplain+ Final NLI Safety Evaluation"
)

print(
    "=" * 72
)


rows = []


for index, case in enumerate(
    cases,
    start=1,
):

    print(
        f"[{index}/{len(cases)}] "
        f"{case['id']}"
    )


    result = check_pair(
        case["evidence"],
        case["statement"],
    )


    available = bool(
        result.get(
            "available"
        )
    )


    deployed_label = (
        result.get(
            "label",
            "unavailable",
        )
        if available
        else "unavailable"
    )


    evaluation_label = (
        deployed_to_eval_label(
            deployed_label
        )
    )


    gold_label = (
        case["label"]
    )


    unsafe_gold = (
        gold_is_unsafe(
            gold_label
        )
    )


    was_flagged = (
        deployment_flagged(
            deployed_label
        )
    )


    # Safety false negative:
    # unsafe gold claim incorrectly allowed through
    # as entailed.
    safety_false_negative = (
        unsafe_gold
        and deployed_label
        == "entailed"
    )


    # Safety false positive:
    # genuinely supported statement was warned/blocked.
    safety_false_positive = (
        gold_label
        == "entailment"
        and was_flagged
    )


    row = {
        "id":
            case["id"],

        "category":
            case.get(
                "category",
                "unspecified",
            ),

        "severity":
            case.get(
                "severity",
                "unspecified",
            ),

        "evidence":
            case["evidence"],

        "statement":
            case["statement"],

        "gold_label":
            gold_label,

        "gold_unsafe":
            unsafe_gold,

        "available":
            available,

        "deployed_label":
            deployed_label,

        "evaluation_label":
            evaluation_label,

        "entailment_score":
            result.get(
                "entailment"
            ),

        "neutral_score":
            result.get(
                "neutral"
            ),

        "contradiction_score":
            result.get(
                "contradiction"
            ),

        "three_class_correct":
            (
                evaluation_label
                == gold_label
            ),

        "flagged":
            was_flagged,

        "safety_false_negative":
            safety_false_negative,

        "safety_false_positive":
            safety_false_positive,

        "error":
            result.get(
                "error"
            ),
    }


    rows.append(
        row
    )


# ============================================================
# AVAILABLE RESULTS
# ============================================================

valid = [
    row
    for row in rows
    if row["available"]
]


if not valid:

    print()
    print(
        "NLI model was unavailable for all cases."
    )

    print(
        "No final result has been generated."
    )

    sys.exit(1)


# ============================================================
# THREE-CLASS PERFORMANCE
# ============================================================

three_class_correct = sum(
    row["three_class_correct"]
    for row in valid
)

three_class_accuracy = (
    three_class_correct
    / len(valid)
)


per_label = {}


for label in GOLD_LABELS:

    tp = sum(
        row["gold_label"] == label
        and row["evaluation_label"] == label
        for row in valid
    )

    fp = sum(
        row["gold_label"] != label
        and row["evaluation_label"] == label
        for row in valid
    )

    fn = sum(
        row["gold_label"] == label
        and row["evaluation_label"] != label
        for row in valid
    )


    precision = safe_div(
        tp,
        tp + fp,
    )

    recall = safe_div(
        tp,
        tp + fn,
    )

    f1 = (
        safe_div(
            2
            * precision
            * recall,
            precision
            + recall,
        )
        if (
            precision
            + recall
        )
        else 0.0
    )


    per_label[label] = {
        "support":
            sum(
                row["gold_label"]
                == label
                for row in valid
            ),

        "precision":
            round4(
                precision
            ),

        "recall":
            round4(
                recall
            ),

        "f1":
            round4(
                f1
            ),
    }


macro_precision = (
    statistics.mean(
        item["precision"]
        for item
        in per_label.values()
    )
)

macro_recall = (
    statistics.mean(
        item["recall"]
        for item
        in per_label.values()
    )
)

macro_f1 = (
    statistics.mean(
        item["f1"]
        for item
        in per_label.values()
    )
)


# ============================================================
# BINARY SAFETY PERFORMANCE
# ============================================================

unsafe_cases = [
    row
    for row in valid
    if row["gold_unsafe"]
]


supported_cases = [
    row
    for row in valid
    if not row["gold_unsafe"]
]


true_positive = sum(
    row["gold_unsafe"]
    and row["flagged"]
    for row in valid
)


false_negative = sum(
    row[
        "safety_false_negative"
    ]
    for row in valid
)


false_positive = sum(
    row[
        "safety_false_positive"
    ]
    for row in valid
)


true_negative = sum(
    (
        not row["gold_unsafe"]
        and not row["flagged"]
    )
    for row in valid
)


safety_precision = safe_div(
    true_positive,
    true_positive
    + false_positive,
)


safety_recall = safe_div(
    true_positive,
    true_positive
    + false_negative,
)


safety_f1 = (
    safe_div(
        2
        * safety_precision
        * safety_recall,
        safety_precision
        + safety_recall,
    )
    if (
        safety_precision
        + safety_recall
    )
    else 0.0
)


false_negative_rate = safe_div(
    false_negative,
    len(
        unsafe_cases
    ),
)


false_positive_rate = safe_div(
    false_positive,
    len(
        supported_cases
    ),
)


# ============================================================
# CATEGORY RESULTS
# ============================================================

by_category = defaultdict(
    list
)


for row in valid:

    by_category[
        row["category"]
    ].append(
        row
    )


category_results = {}


for category, items in sorted(
    by_category.items()
):

    unsafe = [
        item
        for item in items
        if item["gold_unsafe"]
    ]


    category_results[
        category
    ] = {
        "n":
            len(items),

        "three_class_accuracy":
            round4(
                safe_div(
                    sum(
                        item[
                            "three_class_correct"
                        ]
                        for item
                        in items
                    ),
                    len(items),
                )
            ),

        "unsafe_cases":
            len(unsafe),

        "unsafe_flagged":
            sum(
                item["flagged"]
                for item
                in unsafe
            ),

        "unsafe_recall":
            round4(
                safe_div(
                    sum(
                        item["flagged"]
                        for item
                        in unsafe
                    ),
                    len(unsafe),
                )
            )
            if unsafe
            else None,

        "false_negatives":
            sum(
                item[
                    "safety_false_negative"
                ]
                for item
                in unsafe
            ),
    }


# ============================================================
# SEVERITY RESULTS
# ============================================================

by_severity = defaultdict(
    list
)


for row in valid:

    by_severity[
        row["severity"]
    ].append(
        row
    )


severity_results = {}


for severity, items in sorted(
    by_severity.items()
):

    unsafe = [
        item
        for item in items
        if item["gold_unsafe"]
    ]


    severity_results[
        severity
    ] = {
        "n":
            len(items),

        "unsafe_cases":
            len(unsafe),

        "unsafe_flagged":
            sum(
                item["flagged"]
                for item
                in unsafe
            ),

        "unsafe_recall":
            round4(
                safe_div(
                    sum(
                        item["flagged"]
                        for item
                        in unsafe
                    ),
                    len(unsafe),
                )
            )
            if unsafe
            else None,

        "false_negatives":
            sum(
                item[
                    "safety_false_negative"
                ]
                for item
                in unsafe
            ),
    }


# ============================================================
# SCORE STATISTICS
# ============================================================

score_stats = {
    "mean_entailment":
        mean_or_none(
            [
                row[
                    "entailment_score"
                ]
                for row
                in valid
            ]
        ),

    "mean_neutral":
        mean_or_none(
            [
                row[
                    "neutral_score"
                ]
                for row
                in valid
            ]
        ),

    "mean_contradiction":
        mean_or_none(
            [
                row[
                    "contradiction_score"
                ]
                for row
                in valid
            ]
        ),
}


# ============================================================
# FINAL JSON
# ============================================================

result = {
    "evaluation":
        "nli_grounding_safety",

    "description":
        (
            "Evaluates the deployed DeBERTa NLI "
            "threshold logic used by MediExplain+."
        ),

    "n_total":
        len(cases),

    "n_available":
        len(valid),

    "n_unavailable":
        len(cases)
        - len(valid),

    "three_class": {
        "accuracy":
            round4(
                three_class_accuracy
            ),

        "macro_precision":
            round4(
                macro_precision
            ),

        "macro_recall":
            round4(
                macro_recall
            ),

        "macro_f1":
            round4(
                macro_f1
            ),

        "per_label":
            per_label,
    },

    "binary_safety": {
        "unsafe_cases":
            len(
                unsafe_cases
            ),

        "supported_cases":
            len(
                supported_cases
            ),

        "true_positive":
            true_positive,

        "false_negative":
            false_negative,

        "false_positive":
            false_positive,

        "true_negative":
            true_negative,

        "precision":
            round4(
                safety_precision
            ),

        "recall":
            round4(
                safety_recall
            ),

        "f1":
            round4(
                safety_f1
            ),

        "false_negative_rate":
            round4(
                false_negative_rate
            ),

        "false_positive_rate":
            round4(
                false_positive_rate
            ),
    },

    "per_category":
        category_results,

    "per_severity":
        severity_results,

    "score_statistics":
        score_stats,

    "cases":
        rows,
}


JSON_OUT.write_text(
    json.dumps(
        result,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)


# ============================================================
# CSV
# ============================================================

csv_fields = [
    "id",
    "category",
    "severity",
    "gold_label",
    "gold_unsafe",
    "deployed_label",
    "evaluation_label",
    "entailment_score",
    "neutral_score",
    "contradiction_score",
    "three_class_correct",
    "flagged",
    "safety_false_negative",
    "safety_false_positive",
    "evidence",
    "statement",
    "error",
]


with CSV_OUT.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:

    writer = csv.DictWriter(
        handle,
        fieldnames=
            csv_fields,
    )

    writer.writeheader()


    for row in rows:

        writer.writerow(
            {
                field:
                    row.get(
                        field
                    )
                for field
                in csv_fields
            }
        )


# ============================================================
# CONSOLE
# ============================================================

print()
print(
    "-" * 72
)

print(
    f"Available cases:                 "
    f"{len(valid)}"
)

print(
    f"Three-class accuracy:            "
    f"{three_class_accuracy * 100:.1f}%"
)

print(
    f"Macro F1:                        "
    f"{macro_f1 * 100:.1f}%"
)

print()
print(
    "SAFETY FLAG PERFORMANCE"
)

print(
    "-" * 72
)

print(
    f"Unsafe cases:                    "
    f"{len(unsafe_cases)}"
)

print(
    f"Unsafe cases correctly flagged:  "
    f"{true_positive}"
)

print(
    f"Safety recall:                   "
    f"{safety_recall * 100:.1f}%"
)

print(
    f"Safety precision:                "
    f"{safety_precision * 100:.1f}%"
)

print(
    f"Safety F1:                       "
    f"{safety_f1 * 100:.1f}%"
)

print(
    f"Safety false negatives:          "
    f"{false_negative}"
)

print(
    f"FALSE NEGATIVE RATE:             "
    f"{false_negative_rate * 100:.1f}%"
)

print(
    f"False positive rate:             "
    f"{false_positive_rate * 100:.1f}%"
)


print()
print(
    "False negatives requiring review:"
)

false_negative_rows = [
    row
    for row in valid
    if row[
        "safety_false_negative"
    ]
]


if false_negative_rows:

    for row in false_negative_rows:

        print()
        print(
            f"  {row['id']} "
            f"[{row['category']}]"
        )

        print(
            f"    Evidence:  "
            f"{row['evidence']}"
        )

        print(
            f"    Statement: "
            f"{row['statement']}"
        )

else:

    print(
        "  None"
    )


print()
print(
    "Saved:"
)

print(
    f"  {JSON_OUT.relative_to(ROOT)}"
)

print(
    f"  {CSV_OUT.relative_to(ROOT)}"
)