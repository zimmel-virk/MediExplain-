"""
MediExplain+ Clinical Summary Evaluation

Evaluates clinician ratings using:
- PDQI-9
- unsupported additions
- omissions
- substitutions
- medication errors
- dose/frequency/duration errors
- negation/warning-sign errors
- clinically significant error frequency

Input:
    evaluation/data/pdqi_ratings.csv

Output:
    evaluation/results/pdqi.json
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

DATA = ROOT / "evaluation" / "data" / "pdqi_ratings.csv"
OUT = ROOT / "evaluation" / "results" / "pdqi.json"

OUT.parent.mkdir(parents=True, exist_ok=True)


PDQI_DOMAINS = [
    "up_to_date",
    "accurate",
    "thorough",
    "useful",
    "organized",
    "comprehensible",
    "succinct",
    "synthesized",
    "consistent",
]

ERROR_FIELDS = [
    "unsupported_additions",
    "omissions",
    "substitutions",
    "medication_errors",
    "dose_frequency_duration_errors",
    "negation_warning_errors",
]


def mean(values):
    if not values:
        return None
    return round(statistics.mean(values), 3)


def median(values):
    if not values:
        return None
    return round(statistics.median(values), 3)


def integer(value, field, row_number):
    value = (value or "").strip()

    if value == "":
        return 0

    try:
        number = int(value)
    except ValueError:
        raise ValueError(
            f"Row {row_number}: {field} must be an integer."
        )

    if number < 0:
        raise ValueError(
            f"Row {row_number}: {field} cannot be negative."
        )

    return number


def boolean(value):
    value = (value or "").strip().lower()

    return value in {
        "1",
        "true",
        "yes",
        "y",
    }


if not DATA.exists():
    print(f"Missing ratings file: {DATA}")
    sys.exit(1)


ratings = []

with DATA.open(
    "r",
    encoding="utf-8-sig",
    newline="",
) as fh:

    reader = csv.DictReader(fh)

    for row_number, row in enumerate(
        reader,
        start=2,
    ):
        case_id = (
            row.get("case_id") or ""
        ).strip()

        rater_id = (
            row.get("rater_id") or ""
        ).strip()

        # Ignore completely empty rows.
        if not case_id and not rater_id:
            continue

        if not case_id or not rater_id:
            raise ValueError(
                f"Row {row_number}: case_id and rater_id are required."
            )

        scores = {}

        for domain in PDQI_DOMAINS:
            value = (
                row.get(domain) or ""
            ).strip()

            if not value:
                raise ValueError(
                    f"Row {row_number}: missing PDQI score for {domain}."
                )

            try:
                score = int(value)
            except ValueError:
                raise ValueError(
                    f"Row {row_number}: {domain} must be 1-5."
                )

            if score < 1 or score > 5:
                raise ValueError(
                    f"Row {row_number}: {domain} must be 1-5."
                )

            scores[domain] = score

        errors = {
            field: integer(
                row.get(field),
                field,
                row_number,
            )
            for field in ERROR_FIELDS
        }

        total = sum(scores.values())

        ratings.append(
            {
                "case_id": case_id,
                "rater_id": rater_id,
                "scores": scores,
                "pdqi_total": total,
                "errors": errors,
                "clinically_significant_error":
                    boolean(
                        row.get(
                            "clinically_significant_error"
                        )
                    ),
                "comments":
                    (row.get("comments") or "").strip(),
            }
        )


print()
print("=" * 70)
print("MediExplain+ PDQI-9 Clinical Summary Evaluation")
print("=" * 70)


if not ratings:
    print()
    print("PDQI-9 infrastructure is ready.")
    print("No completed doctor ratings have been entered yet.")
    print()
    print(
        "Enter ratings into:"
        f" {DATA.relative_to(ROOT)}"
    )
    print()
    sys.exit(0)


unique_cases = sorted(
    {r["case_id"] for r in ratings}
)

unique_raters = sorted(
    {r["rater_id"] for r in ratings}
)


# ----------------------------------------------------------
# PDQI DOMAIN STATISTICS
# ----------------------------------------------------------

domain_results = {}

for domain in PDQI_DOMAINS:

    values = [
        r["scores"][domain]
        for r in ratings
    ]

    domain_results[domain] = {
        "mean": mean(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
    }


totals = [
    r["pdqi_total"]
    for r in ratings
]


# ----------------------------------------------------------
# PER-CASE STATISTICS
# ----------------------------------------------------------

by_case = defaultdict(list)

for rating in ratings:
    by_case[rating["case_id"]].append(
        rating["pdqi_total"]
    )


per_case = {}

for case_id, values in by_case.items():

    per_case[case_id] = {
        "ratings": len(values),
        "mean_pdqi_total":
            mean(values),
        "min_pdqi_total":
            min(values),
        "max_pdqi_total":
            max(values),
    }


# ----------------------------------------------------------
# FACTUAL ERROR STATISTICS
# ----------------------------------------------------------

error_totals = {}

for field in ERROR_FIELDS:

    values = [
        r["errors"][field]
        for r in ratings
    ]

    error_totals[field] = {
        "total_reported":
            sum(values),
        "mean_per_rating":
            mean(values),
        "ratings_with_error":
            sum(
                1
                for value in values
                if value > 0
            ),
    }


significant_count = sum(
    1
    for r in ratings
    if r["clinically_significant_error"]
)


result = {
    "evaluation": "clinical_summary_pdqi9",
    "ratings": len(ratings),
    "unique_cases": len(unique_cases),
    "unique_raters": len(unique_raters),

    "pdqi": {
        "possible_range": [
            9,
            45,
        ],
        "mean_total":
            mean(totals),
        "median_total":
            median(totals),
        "min_total":
            min(totals),
        "max_total":
            max(totals),
        "mean_percent_of_max":
            round(
                mean(totals) / 45 * 100,
                2,
            ),
        "domains":
            domain_results,
    },

    "factual_errors":
        error_totals,

    "clinically_significant_error": {
        "ratings_flagged":
            significant_count,
        "rating_rate":
            round(
                significant_count
                / len(ratings),
                4,
            ),
    },

    "per_case":
        per_case,

    "individual_ratings":
        ratings,
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
    f"Cases evaluated:       {len(unique_cases)}"
)
print(
    f"Doctors/raters:        {len(unique_raters)}"
)
print(
    f"Total ratings:         {len(ratings)}"
)
print()
print(
    f"Mean PDQI-9:           {mean(totals):.2f} / 45"
)
print(
    f"Median PDQI-9:         {median(totals):.2f} / 45"
)
print(
    f"Minimum:               {min(totals)} / 45"
)
print(
    f"Maximum:               {max(totals)} / 45"
)

print()
print("Domain means")
print("-" * 45)

for domain in PDQI_DOMAINS:
    label = domain.replace(
        "_",
        " ",
    ).title()

    print(
        f"{label:<25}"
        f"{domain_results[domain]['mean']:.2f} / 5"
    )


print()
print("Factual errors")
print("-" * 45)

for field in ERROR_FIELDS:
    label = field.replace(
        "_",
        " ",
    ).title()

    print(
        f"{label:<35}"
        f"{error_totals[field]['total_reported']}"
    )


print()
print(
    "Clinically significant error flags: "
    f"{significant_count}/{len(ratings)} "
    f"({significant_count / len(ratings) * 100:.1f}%)"
)

print()
print(
    "Saved:"
    f" {OUT.relative_to(ROOT)}"
)
