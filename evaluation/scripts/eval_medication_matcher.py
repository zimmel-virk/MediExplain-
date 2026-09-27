"""
MediExplain+ Final Medication Terminology Evaluation

Evaluates the deployed medication_index.suggest() matcher.

Measures:
- Top-1 accuracy
- Top-3 accuracy
- Top-5 accuracy
- Per-category performance
- Hard-negative false-positive rate
- Candidate confidence scores
- Strength compatibility where applicable
- Failure analysis

The benchmark remains independent of the terminology database:
evaluation misspellings are NOT inserted as aliases.

Input:
    evaluation/data/medication_test_set.json

Outputs:
    evaluation/results/medication_matcher_final.json
    evaluation/results/medication_matcher_detailed.csv
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

from app.services.medication_index import (
    extract_strength,
    stats,
    suggest,
)


DATA = (
    ROOT
    / "evaluation"
    / "data"
    / "medication_test_set.json"
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
    / "medication_matcher_final.json"
)

CSV_OUT = (
    RESULTS_DIR
    / "medication_matcher_detailed.csv"
)


# ============================================================
# HELPERS
# ============================================================

def safe_div(
    numerator: int | float,
    denominator: int | float,
):
    if not denominator:
        return None

    return numerator / denominator


def round4(
    value,
):
    if value is None:
        return None

    return round(
        value,
        4,
    )


def percentage(
    value,
):
    if value is None:
        return "n/a"

    return (
        f"{value * 100:.1f}%"
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
        statistics.mean(values),
        4,
    )


def candidate_text(
    candidate: dict,
) -> str:

    fields = (
        "display_name",
        "generic_name",
        "brand_name",
        "matched_via",
        "active_ingredient",
    )

    return " ".join(
        str(
            candidate.get(field)
            or ""
        )
        for field in fields
    ).lower()


def expected_terms(
    case: dict,
) -> list[str]:

    # New format supports several acceptable names,
    # e.g. paracetamol / acetaminophen.
    values = case.get(
        "expected_any"
    )

    if values:
        return [
            str(value).lower()
            for value in values
        ]

    old = case.get(
        "expected_contains"
    )

    if old is None:
        return []

    return [
        str(old).lower()
    ]


def matches_expected(
    candidate: dict,
    terms: list[str],
) -> bool:

    haystack = candidate_text(
        candidate
    )

    return any(
        term in haystack
        for term in terms
    )


# ============================================================
# LOAD / CHECK DATABASE
# ============================================================

index_stats = stats()


print()
print(
    "=" * 78
)

print(
    "MediExplain+ Medication Terminology Evaluation"
)

print(
    "=" * 78
)

print()
print(
    f"Medication concepts: {index_stats.get('concepts', 0):,}"
)

print(
    f"Aliases:             {index_stats.get('aliases', 0):,}"
)

print(
    "Sources:             "
    + ", ".join(
        index_stats.get(
            "sources",
            [],
        )
    )
)


if index_stats.get(
    "concepts",
    0,
) < 100:

    print()
    print(
        "Medication index is not sufficiently populated."
    )

    print(
        "Run:"
    )

    print(
        "  cd backend && "
        "python -m scripts.setup_medication_data"
    )

    sys.exit(2)


# ============================================================
# LOAD DATASET
# ============================================================

if not DATA.exists():

    print(
        f"Missing test set: "
        f"{DATA.relative_to(ROOT)}"
    )

    sys.exit(2)


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

    print(
        "Medication test set is empty."
    )

    sys.exit(2)


# ============================================================
# RUN TESTS
# ============================================================

rows = []


for number, case in enumerate(
    cases,
    start=1,
):

    query = (
        case.get(
            "query",
            "",
        )
        .strip()
    )

    category = (
        case.get(
            "category",
            "unspecified",
        )
    )

    terms = expected_terms(
        case
    )

    is_negative = (
        len(terms)
        == 0
    )


    print(
        f"[{number:02d}/{len(cases):02d}] "
        f"{category:<16} "
        f"{query}"
    )


    candidates = suggest(
        query,
        top_k=5,
    )


    top_candidate = (
        candidates[0]
        if candidates
        else None
    )


    # --------------------------------------------------------
    # HARD NEGATIVE
    # --------------------------------------------------------

    if is_negative:

        false_positive = bool(
            candidates
        )

        rows.append(
            {
                "query":
                    query,

                "category":
                    category,

                "case_type":
                    "hard_negative",

                "expected":
                    None,

                "candidate_count":
                    len(candidates),

                "rank":
                    None,

                "top1":
                    None,

                "top3":
                    None,

                "top5":
                    None,

                "false_positive":
                    false_positive,

                "query_strength":
                    extract_strength(
                        query
                    ),

                "top_score":
                    (
                        top_candidate.get(
                            "score"
                        )
                        if top_candidate
                        else None
                    ),

                "top_display_name":
                    (
                        top_candidate.get(
                            "display_name"
                        )
                        if top_candidate
                        else None
                    ),

                "top_generic_name":
                    (
                        top_candidate.get(
                            "generic_name"
                        )
                        if top_candidate
                        else None
                    ),

                "top_brand_name":
                    (
                        top_candidate.get(
                            "brand_name"
                        )
                        if top_candidate
                        else None
                    ),

                "top_source":
                    (
                        top_candidate.get(
                            "source"
                        )
                        if top_candidate
                        else None
                    ),

                "top_matched_via":
                    (
                        top_candidate.get(
                            "matched_via"
                        )
                        if top_candidate
                        else None
                    ),

                "top_strength_compatible":
                    (
                        top_candidate.get(
                            "strength_compatible"
                        )
                        if top_candidate
                        else None
                    ),

                "candidates":
                    candidates,
            }
        )

        continue


    # --------------------------------------------------------
    # POSITIVE CASE
    # --------------------------------------------------------

    rank = 0
    matched_candidate = None


    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        if matches_expected(
            candidate,
            terms,
        ):

            rank = index
            matched_candidate = (
                candidate
            )

            break


    query_strength = (
        extract_strength(
            query
        )
    )


    rows.append(
        {
            "query":
                query,

            "category":
                category,

            "case_type":
                "positive",

            "expected":
                terms,

            "candidate_count":
                len(candidates),

            "rank":
                rank,

            "top1":
                rank == 1,

            "top3":
                1 <= rank <= 3,

            "top5":
                1 <= rank <= 5,

            "false_positive":
                None,

            "query_strength":
                query_strength,

            "matched_strength_compatible":
                (
                    matched_candidate.get(
                        "strength_compatible"
                    )
                    if matched_candidate
                    else None
                ),

            "matched_score":
                (
                    matched_candidate.get(
                        "score"
                    )
                    if matched_candidate
                    else None
                ),

            "top_score":
                (
                    top_candidate.get(
                        "score"
                    )
                    if top_candidate
                    else None
                ),

            "top_display_name":
                (
                    top_candidate.get(
                        "display_name"
                    )
                    if top_candidate
                    else None
                ),

            "top_generic_name":
                (
                    top_candidate.get(
                        "generic_name"
                    )
                    if top_candidate
                    else None
                ),

            "top_brand_name":
                (
                    top_candidate.get(
                        "brand_name"
                    )
                    if top_candidate
                    else None
                ),

            "top_source":
                (
                    top_candidate.get(
                        "source"
                    )
                    if top_candidate
                    else None
                ),

            "top_matched_via":
                (
                    top_candidate.get(
                        "matched_via"
                    )
                    if top_candidate
                    else None
                ),

            "top_strength_compatible":
                (
                    top_candidate.get(
                        "strength_compatible"
                    )
                    if top_candidate
                    else None
                ),

            "candidates":
                candidates,
        }
    )


# ============================================================
# SPLIT
# ============================================================

positive = [
    row
    for row in rows
    if row["case_type"]
    == "positive"
]

negative = [
    row
    for row in rows
    if row["case_type"]
    == "hard_negative"
]


# ============================================================
# OVERALL POSITIVE METRICS
# ============================================================

top1_accuracy = safe_div(
    sum(
        bool(row["top1"])
        for row in positive
    ),
    len(positive),
)

top3_accuracy = safe_div(
    sum(
        bool(row["top3"])
        for row in positive
    ),
    len(positive),
)

top5_accuracy = safe_div(
    sum(
        bool(row["top5"])
        for row in positive
    ),
    len(positive),
)


# ============================================================
# HARD NEGATIVE METRICS
# ============================================================

false_positives = sum(
    bool(
        row[
            "false_positive"
        ]
    )
    for row in negative
)


hard_negative_fpr = safe_div(
    false_positives,
    len(negative),
)


hard_negative_specificity = (
    1 - hard_negative_fpr
    if hard_negative_fpr
    is not None
    else None
)


# ============================================================
# STRENGTH COMPATIBILITY
# ============================================================

strength_cases = [
    row
    for row in positive
    if row[
        "query_strength"
    ]
    is not None
]


matched_strength_cases = [
    row
    for row in strength_cases
    if row[
        "matched_strength_compatible"
    ]
    is not None
]


strength_compatibility_rate = safe_div(
    sum(
        bool(
            row[
                "matched_strength_compatible"
            ]
        )
        for row
        in matched_strength_cases
    ),
    len(
        matched_strength_cases
    ),
)


# ============================================================
# PER-CATEGORY
# ============================================================

groups = defaultdict(
    list
)


for row in rows:

    groups[
        row["category"]
    ].append(
        row
    )


per_category = {}


for category, items in sorted(
    groups.items()
):

    pos = [
        item
        for item in items
        if item[
            "case_type"
        ]
        == "positive"
    ]

    neg = [
        item
        for item in items
        if item[
            "case_type"
        ]
        == "hard_negative"
    ]


    result = {
        "n":
            len(items),

        "n_positive":
            len(pos),

        "n_negative":
            len(neg),
    }


    if pos:

        result[
            "top1_accuracy"
        ] = round4(
            safe_div(
                sum(
                    bool(
                        item["top1"]
                    )
                    for item in pos
                ),
                len(pos),
            )
        )

        result[
            "top3_accuracy"
        ] = round4(
            safe_div(
                sum(
                    bool(
                        item["top3"]
                    )
                    for item in pos
                ),
                len(pos),
            )
        )

        result[
            "top5_accuracy"
        ] = round4(
            safe_div(
                sum(
                    bool(
                        item["top5"]
                    )
                    for item in pos
                ),
                len(pos),
            )
        )


    if neg:

        result[
            "false_positive_rate"
        ] = round4(
            safe_div(
                sum(
                    bool(
                        item[
                            "false_positive"
                        ]
                    )
                    for item in neg
                ),
                len(neg),
            )
        )


    per_category[
        category
    ] = result


# ============================================================
# FAILURE ANALYSIS
# ============================================================

positive_failures = [
    row
    for row in positive
    if not row["top3"]
]


negative_failures = [
    row
    for row in negative
    if row[
        "false_positive"
    ]
]


# ============================================================
# FINAL RESULT
# ============================================================

result = {
    "evaluation":
        "medication_terminology_matcher",

    "dataset_note":
        payload.get(
            "_note"
        ),

    "terminology_stats":
        index_stats,

    "n_total":
        len(rows),

    "n_positive":
        len(positive),

    "n_hard_negative":
        len(negative),

    "positive_metrics": {
        "top1_accuracy":
            round4(
                top1_accuracy
            ),

        "top3_accuracy":
            round4(
                top3_accuracy
            ),

        "top5_accuracy":
            round4(
                top5_accuracy
            ),

        "mean_top_candidate_score":
            mean_or_none(
                row[
                    "top_score"
                ]
                for row
                in positive
            ),

        "strength_cases":
            len(
                strength_cases
            ),

        "strength_compatibility_rate":
            round4(
                strength_compatibility_rate
            ),
    },

    "hard_negative_metrics": {
        "false_positives":
            false_positives,

        "false_positive_rate":
            round4(
                hard_negative_fpr
            ),

        "specificity":
            round4(
                hard_negative_specificity
            ),

        "mean_false_positive_score":
            mean_or_none(
                row[
                    "top_score"
                ]
                for row
                in negative_failures
            ),
    },

    "per_category":
        per_category,

    "failure_summary": {
        "positive_top3_failures":
            len(
                positive_failures
            ),

        "hard_negative_false_positives":
            len(
                negative_failures
            ),
    },

    "per_case":
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

CSV_FIELDS = [
    "query",
    "category",
    "case_type",
    "expected",
    "candidate_count",
    "rank",
    "top1",
    "top3",
    "top5",
    "false_positive",
    "query_strength",
    "matched_strength_compatible",
    "matched_score",
    "top_score",
    "top_display_name",
    "top_generic_name",
    "top_brand_name",
    "top_source",
    "top_matched_via",
    "top_strength_compatible",
]


with CSV_OUT.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:

    writer = csv.DictWriter(
        handle,
        fieldnames=
            CSV_FIELDS,
    )

    writer.writeheader()


    for row in rows:

        flat = {}

        for field in CSV_FIELDS:

            value = row.get(
                field
            )

            if isinstance(
                value,
                list,
            ):
                value = (
                    " | ".join(
                        str(x)
                        for x in value
                    )
                )

            flat[
                field
            ] = value

        writer.writerow(
            flat
        )


# ============================================================
# CONSOLE SUMMARY
# ============================================================

print()
print(
    "=" * 78
)

print(
    "FINAL RESULTS"
)

print(
    "=" * 78
)

print()
print(
    f"Total cases:                     {len(rows)}"
)

print(
    f"Positive medication cases:       {len(positive)}"
)

print(
    f"Hard negatives:                  {len(negative)}"
)

print()
print(
    f"Top-1 accuracy:                  {percentage(top1_accuracy)}"
)

print(
    f"Top-3 accuracy:                  {percentage(top3_accuracy)}"
)

print(
    f"Top-5 accuracy:                  {percentage(top5_accuracy)}"
)

print(
    f"Strength compatibility:          {percentage(strength_compatibility_rate)}"
)

print()
print(
    f"Hard-negative false positives:   "
    f"{false_positives}/{len(negative)}"
)

print(
    f"Hard-negative FP rate:           {percentage(hard_negative_fpr)}"
)

print(
    f"Hard-negative specificity:       {percentage(hard_negative_specificity)}"
)


print()
print(
    "PER-CATEGORY"
)

print(
    "-" * 78
)


for category, metrics in per_category.items():

    print(
        f"{category:<22}"
        f"N={metrics['n']:<4}",
        end="",
    )

    if (
        "top1_accuracy"
        in metrics
    ):

        print(
            f"Top1="
            f"{percentage(metrics['top1_accuracy'])}  "
            f"Top3="
            f"{percentage(metrics['top3_accuracy'])}",
            end="",
        )

    if (
        "false_positive_rate"
        in metrics
    ):

        print(
            f"FP="
            f"{percentage(metrics['false_positive_rate'])}",
            end="",
        )

    print()


print()
print(
    "FAILURES REQUIRING REVIEW"
)

print(
    "-" * 78
)


if positive_failures:

    print()
    print(
        "Positive cases not found in Top-3:"
    )

    for row in positive_failures:

        print(
            f"  - {row['query']}"
            f" -> top result: "
            f"{row['top_display_name'] or 'NO MATCH'}"
        )

else:

    print(
        "No positive Top-3 failures."
    )


if negative_failures:

    print()
    print(
        "Hard negatives incorrectly matched:"
    )

    for row in negative_failures:

        print(
            f"  - {row['query']}"
            f" -> {row['top_display_name']}"
            f" (score={row['top_score']})"
        )

else:

    print(
        "No hard-negative false positives."
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