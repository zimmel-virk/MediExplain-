"""
MediExplain+ Final Translation Evaluation

Evaluates:
- BLEU
- chrF
- numeric preservation
- medication preservation
- deployed script-policy result
- Arabic-derived target-script presence
- Devanagari leakage
- Gurmukhi leakage
- deployed semantic back-translation check
- deployed translation quality decision

Final targets:
    Urdu               ur
    Punjabi Shahmukhi  pa_shah
    Pashto             ps
    Sindhi             sd
    Arabic             ar

Input:
    evaluation/data/translation_test_set.json

Outputs:
    evaluation/results/translation.json
    evaluation/results/translation_detailed.csv
    evaluation/results/translation_human_review.csv

COMET is intentionally left for the final-reference stage because
it requires a separate large evaluation model. BLEU/chrF and all
safety infrastructure can be prepared now.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys

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

DATA = (
    ROOT
    / "evaluation"
    / "data"
    / "translation_test_set.json"
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
    / "translation.json"
)

CSV_OUT = (
    RESULTS_DIR
    / "translation_detailed.csv"
)

HUMAN_OUT = (
    RESULTS_DIR
    / "translation_human_review.csv"
)


# ============================================================
# FINAL TARGET LANGUAGES
# ============================================================

TARGETS = {
    "ur": "Urdu",
    "pa_shah": "Punjabi Shahmukhi",
    "ps": "Pashto",
    "sd": "Sindhi",
    "ar": "Arabic",
}

ARABIC_SCRIPT_TARGETS = set(
    TARGETS.keys()
)


# ============================================================
# CREATE STARTER DATASET
# ============================================================

if not DATA.exists():

    base_cases = [
        {
            "id": "tx_01",
            "category": "diagnosis",
            "source":
                "You have a viral throat infection.",
            "structured": {},
        },
        {
            "id": "tx_02",
            "category": "medicine_dose_frequency_duration",
            "source":
                "Take Panadol 500 mg, one tablet twice daily "
                "after food for 5 days.",
            "structured": {
                "medications": [
                    {
                        "name": "Panadol",
                        "strength": "500 mg",
                        "dose": "one tablet",
                        "frequency": "twice daily",
                        "duration": "5 days",
                    }
                ]
            },
        },
        {
            "id": "tx_03",
            "category": "medicine_interval",
            "source":
                "Take Augmentin 625 mg every 8 hours for 7 days.",
            "structured": {
                "medications": [
                    {
                        "name": "Augmentin",
                        "strength": "625 mg",
                        "frequency": "every 8 hours",
                        "duration": "7 days",
                    }
                ]
            },
        },
        {
            "id": "tx_04",
            "category": "negation_warning",
            "source":
                "Do not take Ibuprofen if you develop "
                "stomach bleeding.",
            "structured": {
                "medications": [
                    {
                        "name": "Ibuprofen",
                    }
                ]
            },
        },
        {
            "id": "tx_05",
            "category": "symptom_negation",
            "source":
                "You do not have chest pain or shortness of breath.",
            "structured": {},
        },
        {
            "id": "tx_06",
            "category": "follow_up",
            "source":
                "Return to the clinic in 7 days for follow-up.",
            "structured": {},
        },
        {
            "id": "tx_07",
            "category": "warning_sign",
            "source":
                "If your fever rises above 39 degrees, "
                "seek urgent medical review.",
            "structured": {},
        },
        {
            "id": "tx_08",
            "category": "medicine_timing",
            "source":
                "Take Omeprazole 20 mg once daily before "
                "breakfast for 14 days.",
            "structured": {
                "medications": [
                    {
                        "name": "Omeprazole",
                        "strength": "20 mg",
                        "frequency": "once daily",
                        "timing": "before breakfast",
                        "duration": "14 days",
                    }
                ]
            },
        },
        {
            "id": "tx_09",
            "category": "emergency_warning",
            "source":
                "Stop the medicine and seek help if you develop "
                "swelling or difficulty breathing.",
            "structured": {},
        },
        {
            "id": "tx_10",
            "category": "food_instruction",
            "source":
                "Do not take this medicine on an empty stomach.",
            "structured": {},
        },
    ]

    language_pairs = []

    for target in TARGETS:

        language_pairs.append(
            {
                "source_lang": "en",
                "target_lang": target,
                "pairs": [
                    {
                        **case,
                        "reference": "",
                        "reference_reviewed_by": "",
                    }
                    for case in base_cases
                ],
            }
        )

    starter = {
        "_comment":
            (
                "Reference translations must be checked by a "
                "bilingual clinician or competent bilingual reviewer. "
                "Do not enter AI-generated text as the gold reference."
            ),
        "language_pairs":
            language_pairs,
    }

    DATA.write_text(
        json.dumps(
            starter,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 76)
    print("MediExplain+ Translation Evaluation")
    print("=" * 76)
    print()
    print(
        "Created translation evaluation template:"
    )
    print(
        f"  {DATA.relative_to(ROOT)}"
    )
    print()
    print(
        "It contains 10 clinical cases for each "
        "of the 5 translated languages."
    )
    print()
    print(
        "Reference translations can be filled later."
    )

    sys.exit(0)


# ============================================================
# DEPENDENCY
# ============================================================

try:
    import sacrebleu

except ImportError:

    print(
        "Missing dependency: sacrebleu\n\n"
        "Install using:\n"
        "    pip install sacrebleu",
        file=sys.stderr,
    )

    sys.exit(1)


# ============================================================
# PROJECT SERVICES
# ============================================================

from app.services import translation as tx_svc

from app.services.script_policy import (
    contains_arabic_script,
    contains_devanagari,
    contains_gurmukhi,
)


# ============================================================
# HELPERS
# ============================================================

def rate(
    values,
):
    values = list(values)

    if not values:
        return None

    return round(
        sum(
            bool(x)
            for x in values
        ) / len(values),
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
        statistics.mean(values),
        3,
    )


def pct(
    value,
):
    if value is None:
        return "n/a"

    return (
        f"{value * 100:.1f}%"
    )


# ============================================================
# LOAD DATA
# ============================================================

data = json.loads(
    DATA.read_text(
        encoding="utf-8",
    )
)

groups = data.get(
    "language_pairs",
    [],
)


if not groups:

    print(
        "No language pairs found in "
        "translation_test_set.json"
    )

    sys.exit(1)


# ============================================================
# VALIDATE LANGUAGE COVERAGE
# ============================================================

present_targets = {
    group.get("target_lang")
    for group in groups
}

missing_targets = (
    set(TARGETS.keys())
    - present_targets
)


if missing_targets:

    print(
        "WARNING: translation test set is missing:"
    )

    for target in sorted(
        missing_targets
    ):
        print(
            f"  {target} - {TARGETS[target]}"
        )


# ============================================================
# RUN
# ============================================================

print()
print(
    "=" * 88
)

print(
    "MediExplain+ Final Translation Evaluation"
)

print(
    "=" * 88
)


all_rows = []
summary = {}


for group in groups:

    source_lang = (
        group.get(
            "source_lang",
            "en",
        )
    )

    target_lang = (
        group.get(
            "target_lang"
        )
    )


    if target_lang not in TARGETS:

        print(
            f"\nSkipping unsupported evaluation target: "
            f"{target_lang}"
        )

        continue


    pairs = group.get(
        "pairs",
        [],
    )


    valid = [
        pair
        for pair in pairs
        if (
            pair.get(
                "reference",
                ""
            ).strip()
        )
    ]


    if not valid:

        print(
            f"\n{source_lang} -> "
            f"{target_lang} "
            f"({TARGETS[target_lang]}): "
            "no validated references yet."
        )

        continue


    print()
    print(
        f"{source_lang} -> "
        f"{target_lang} "
        f"({TARGETS[target_lang]})"
    )

    print(
        "-" * 88
    )


    pair_rows = []


    for index, pair in enumerate(
        valid,
        start=1,
    ):

        case_id = pair.get(
            "id",
            f"{target_lang}_{index:03d}",
        )

        category = pair.get(
            "category",
            "unspecified",
        )

        source = (
            pair["source"]
            .strip()
        )

        reference = (
            pair["reference"]
            .strip()
        )

        structured = (
            pair.get(
                "structured"
            )
            or {}
        )


        print(
            f"[{index}/{len(valid)}] "
            f"{case_id} "
            f"({category})"
        )


        # ----------------------------------------------------
        # IMPORTANT:
        # Evaluate the actual deployed translation function,
        # not only the low-level translate() function.
        # ----------------------------------------------------

        try:

            tx = (
                tx_svc
                .translate_with_metadata(
                    source,
                    source_lang,
                    target_lang,
                    structured,
                )
            )

        except Exception as exc:

            row = {
                "id": case_id,
                "category": category,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "source": source,
                "reference": reference,
                "hypothesis": "",
                "error": str(exc),
            }

            all_rows.append(
                row
            )

            pair_rows.append(
                row
            )

            print(
                f"  FAILED: {exc}"
            )

            continue


        hypothesis = (
            tx.get(
                "translated"
            )
            or ""
        ).strip()


        if not hypothesis:

            row = {
                "id": case_id,
                "category": category,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "source": source,
                "reference": reference,
                "hypothesis": "",
                "quality":
                    tx.get(
                        "quality"
                    ),
                "error":
                    "Translation returned empty text",
            }

            all_rows.append(
                row
            )

            pair_rows.append(
                row
            )

            print(
                "  FAILED: empty translation"
            )

            continue


        # ----------------------------------------------------
        # REFERENCE METRICS
        # ----------------------------------------------------

        bleu = (
            sacrebleu
            .sentence_bleu(
                hypothesis,
                [reference],
            )
            .score
        )

        chrf = (
            sacrebleu
            .sentence_chrf(
                hypothesis,
                [reference],
            )
            .score
        )


        # ----------------------------------------------------
        # SCRIPT EVALUATION
        # ----------------------------------------------------

        devanagari_present = (
            contains_devanagari(
                hypothesis
            )
        )

        gurmukhi_present = (
            contains_gurmukhi(
                hypothesis
            )
        )

        arabic_script_present = (
            contains_arabic_script(
                hypothesis
            )
            if (
                target_lang
                in ARABIC_SCRIPT_TARGETS
            )
            else None
        )


        forbidden_script_absent = (
            not devanagari_present
            and not gurmukhi_present
        )


        target_script_valid = (
            bool(
                tx.get(
                    "script_valid"
                )
            )
            and forbidden_script_absent
            and (
                bool(
                    arabic_script_present
                )
                if (
                    target_lang
                    in ARABIC_SCRIPT_TARGETS
                )
                else True
            )
        )


        numeric_preserved = bool(
            tx.get(
                "numeric_preserved"
            )
        )


        medication_preserved = bool(
            tx.get(
                "medication_preserved"
            )
        )


        semantic_status = (
            tx.get(
                "semantic_status"
            )
            or "unavailable"
        )


        semantic_score = (
            tx.get(
                "semantic_score"
            )
        )


        # Punjabi Shahmukhi has no native NLLB source code
        # for safe back-translation in this implementation.
        semantic_manual_review_expected = (
            target_lang
            == "pa_shah"
            and semantic_status
            == "unavailable"
        )


        # Independent integrity measure for evaluation.
        integrity_pass = (
            numeric_preserved
            and medication_preserved
            and target_script_valid
        )


        row = {
            "id":
                case_id,

            "category":
                category,

            "source_lang":
                source_lang,

            "target_lang":
                target_lang,

            "target_name":
                TARGETS[
                    target_lang
                ],

            "reference_reviewed_by":
                pair.get(
                    "reference_reviewed_by",
                    "",
                ),

            "source":
                source,

            "reference":
                reference,

            "hypothesis":
                hypothesis,

            "bleu":
                round(
                    bleu,
                    2,
                ),

            "chrf":
                round(
                    chrf,
                    2,
                ),

            "numeric_preserved":
                numeric_preserved,

            "medication_preserved":
                medication_preserved,

            "deployed_script_valid":
                bool(
                    tx.get(
                        "script_valid"
                    )
                ),

            "arabic_script_present":
                arabic_script_present,

            "devanagari_present":
                devanagari_present,

            "gurmukhi_present":
                gurmukhi_present,

            "forbidden_script_absent":
                forbidden_script_absent,

            "target_script_valid":
                target_script_valid,

            "semantic_status":
                semantic_status,

            "semantic_score":
                semantic_score,

            "semantic_manual_review_expected":
                semantic_manual_review_expected,

            "quality":
                tx.get(
                    "quality"
                ),

            "back_translation":
                tx.get(
                    "back_translation"
                ),

            "integrity_pass":
                integrity_pass,

            "error":
                None,
        }


        all_rows.append(
            row
        )

        pair_rows.append(
            row
        )


        print(
            f"  BLEU: "
            f"{bleu:.2f}"
        )

        print(
            f"  chrF: "
            f"{chrf:.2f}"
        )

        print(
            "  numeric preserved: "
            f"{numeric_preserved}"
        )

        print(
            "  medication preserved: "
            f"{medication_preserved}"
        )

        print(
            "  target script valid: "
            f"{target_script_valid}"
        )

        print(
            "  semantic status: "
            f"{semantic_status}"
        )

        print(
            "  deployed quality: "
            f"{tx.get('quality')}"
        )


    # ========================================================
    # LANGUAGE SUMMARY
    # ========================================================

    successful = [
        row
        for row in pair_rows
        if not row.get(
            "error"
        )
    ]


    if not successful:
        continue


    hypotheses = [
        row["hypothesis"]
        for row in successful
    ]

    references = [[
        row["reference"]
        for row in successful
    ]]


    corpus_bleu = (
        sacrebleu
        .corpus_bleu(
            hypotheses,
            references,
        )
        .score
    )


    corpus_chrf = (
        sacrebleu
        .corpus_chrf(
            hypotheses,
            references,
        )
        .score
    )


    pair_name = (
        f"{source_lang}"
        f"->{target_lang}"
    )


    summary[
        pair_name
    ] = {
        "language":
            TARGETS[
                target_lang
            ],

        "n":
            len(
                successful
            ),

        "corpus_bleu":
            round(
                corpus_bleu,
                2,
            ),

        "corpus_chrf":
            round(
                corpus_chrf,
                2,
            ),

        "mean_sentence_bleu":
            round(
                statistics.mean(
                    row["bleu"]
                    for row
                    in successful
                ),
                2,
            ),

        "mean_sentence_chrf":
            round(
                statistics.mean(
                    row["chrf"]
                    for row
                    in successful
                ),
                2,
            ),

        "numeric_preservation_rate":
            rate(
                row[
                    "numeric_preserved"
                ]
                for row
                in successful
            ),

        "medication_preservation_rate":
            rate(
                row[
                    "medication_preserved"
                ]
                for row
                in successful
            ),

        "target_script_valid_rate":
            rate(
                row[
                    "target_script_valid"
                ]
                for row
                in successful
            ),

        "devanagari_leakage_rate":
            rate(
                row[
                    "devanagari_present"
                ]
                for row
                in successful
            ),

        "gurmukhi_leakage_rate":
            rate(
                row[
                    "gurmukhi_present"
                ]
                for row
                in successful
            ),

        "integrity_pass_rate":
            rate(
                row[
                    "integrity_pass"
                ]
                for row
                in successful
            ),

        "mean_semantic_score":
            mean_or_none(
                row[
                    "semantic_score"
                ]
                for row
                in successful
            ),

        "semantic_pass_rate":
            rate(
                row[
                    "semantic_status"
                ]
                == "pass"
                for row
                in successful
                if not row[
                    "semantic_manual_review_expected"
                ]
            ),
    }


# ============================================================
# NO REFERENCES YET
# ============================================================

valid_rows = [
    row
    for row in all_rows
    if not row.get(
        "error"
    )
]


if not valid_rows:

    print()
    print(
        "=" * 88
    )

    print(
        "Translation evaluation infrastructure is ready."
    )

    print(
        "No bilingual/clinician-validated reference "
        "translations have been entered yet."
    )

    print()
    print(
        "Fill references later in:"
    )

    print(
        f"  {DATA.relative_to(ROOT)}"
    )

    print()

    sys.exit(0)


# ============================================================
# DETAILED CSV
# ============================================================

DETAIL_FIELDS = [
    "id",
    "category",
    "source_lang",
    "target_lang",
    "target_name",
    "reference_reviewed_by",
    "bleu",
    "chrf",
    "numeric_preserved",
    "medication_preserved",
    "deployed_script_valid",
    "arabic_script_present",
    "devanagari_present",
    "gurmukhi_present",
    "forbidden_script_absent",
    "target_script_valid",
    "semantic_status",
    "semantic_score",
    "semantic_manual_review_expected",
    "quality",
    "integrity_pass",
    "source",
    "reference",
    "hypothesis",
    "back_translation",
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
            DETAIL_FIELDS,
    )

    writer.writeheader()

    for row in all_rows:

        writer.writerow(
            {
                field:
                    row.get(
                        field
                    )
                for field
                in DETAIL_FIELDS
            }
        )


# ============================================================
# HUMAN REVIEW SHEET
# ============================================================

HUMAN_FIELDS = [
    "id",
    "target_lang",
    "language",
    "category",
    "source",
    "reference",
    "hypothesis",
    "clarity_1_to_5",
    "clinical_meaning_1_to_5",
    "medicine_preserved_yes_no_na",
    "dose_preserved_yes_no_na",
    "frequency_preserved_yes_no_na",
    "duration_preserved_yes_no_na",
    "negation_preserved_yes_no_na",
    "warning_sign_preserved_yes_no_na",
    "overall_safe_yes_no",
    "reviewer_id",
    "comments",
]


with HUMAN_OUT.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:

    writer = csv.DictWriter(
        handle,
        fieldnames=
            HUMAN_FIELDS,
    )

    writer.writeheader()


    for row in valid_rows:

        writer.writerow(
            {
                "id":
                    row["id"],

                "target_lang":
                    row[
                        "target_lang"
                    ],

                "language":
                    row[
                        "target_name"
                    ],

                "category":
                    row[
                        "category"
                    ],

                "source":
                    row[
                        "source"
                    ],

                "reference":
                    row[
                        "reference"
                    ],

                "hypothesis":
                    row[
                        "hypothesis"
                    ],

                "clarity_1_to_5":
                    "",

                "clinical_meaning_1_to_5":
                    "",

                "medicine_preserved_yes_no_na":
                    "",

                "dose_preserved_yes_no_na":
                    "",

                "frequency_preserved_yes_no_na":
                    "",

                "duration_preserved_yes_no_na":
                    "",

                "negation_preserved_yes_no_na":
                    "",

                "warning_sign_preserved_yes_no_na":
                    "",

                "overall_safe_yes_no":
                    "",

                "reviewer_id":
                    "",

                "comments":
                    "",
            }
        )


# ============================================================
# JSON
# ============================================================

result = {
    "evaluation":
        "translation_quality_and_safety",

    "targets":
        TARGETS,

    "per_language":
        summary,

    "per_case":
        all_rows,

    "human_review_file":
        str(
            HUMAN_OUT.relative_to(
                ROOT
            )
        ),

    "comet_status":
        (
            "Pending final validated references; "
            "COMET is intentionally not fabricated "
            "or estimated."
        ),
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
# CONSOLE SUMMARY
# ============================================================

print()
print(
    "=" * 102
)

print(
    "FINAL TRANSLATION SUMMARY"
)

print(
    "=" * 102
)

print(
    f"{'Language':<23}"
    f"{'N':>4}"
    f"{'BLEU':>9}"
    f"{'chrF':>9}"
    f"{'Numbers':>11}"
    f"{'Meds':>10}"
    f"{'Script':>10}"
    f"{'Integrity':>12}"
)

print(
    "-" * 102
)


for pair_name, metrics in summary.items():

    print(
        f"{metrics['language']:<23}"
        f"{metrics['n']:>4}"
        f"{metrics['corpus_bleu']:>9.2f}"
        f"{metrics['corpus_chrf']:>9.2f}"
        f"{pct(metrics['numeric_preservation_rate']):>11}"
        f"{pct(metrics['medication_preservation_rate']):>10}"
        f"{pct(metrics['target_script_valid_rate']):>10}"
        f"{pct(metrics['integrity_pass_rate']):>12}"
    )


print()
print(
    "Results:"
)

print(
    f"  {JSON_OUT.relative_to(ROOT)}"
)

print(
    f"  {CSV_OUT.relative_to(ROOT)}"
)

print(
    f"  {HUMAN_OUT.relative_to(ROOT)}"
)