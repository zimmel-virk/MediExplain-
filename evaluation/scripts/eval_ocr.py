"""
MediExplain+ Final Prescription OCR Evaluation

Evaluates the actual deployed OCR service.

Raw OCR metrics:
- WER
- CER
- OCR confidence
- low-confidence warning rate
- number retention
- medication-name retention
- OCR engine selected

Optional structured evaluation:
- medicine-name accuracy
- strength accuracy
- dose accuracy
- frequency accuracy
- duration accuracy
- instruction accuracy
- overall structured-field accuracy

Dataset layout:

evaluation/data/ocr_prescriptions/

    printed_01.jpg
    printed_01.txt
    printed_01.fields.json

    handwritten_01.jpg
    handwritten_01.txt
    handwritten_01.fields.json

Use --structured to also run the LLM structuring stage:

    python evaluation/scripts/eval_ocr.py --structured

Outputs:

    evaluation/results/ocr.json
    evaluation/results/ocr_detailed.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import statistics
import sys
import unicodedata

from collections import Counter
from difflib import SequenceMatcher
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

DATA_DIR = (
    ROOT
    / "evaluation"
    / "data"
    / "ocr_prescriptions"
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

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

JSON_OUT = (
    RESULTS_DIR
    / "ocr.json"
)

CSV_OUT = (
    RESULTS_DIR
    / "ocr_detailed.csv"
)


# ============================================================
# PROJECT OCR SERVICE
# ============================================================

from app.services import ocr as ocr_service


# ============================================================
# OPTIONAL JIWER
# ============================================================

try:
    from jiwer import cer, wer

except ImportError:

    print(
        "Missing dependency: jiwer\n"
        "Install using:\n"
        "    pip install jiwer",
        file=sys.stderr,
    )

    sys.exit(1)


# ============================================================
# IMAGE TYPES
# ============================================================

IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".heic",
    ".heif",
}


# ============================================================
# NORMALISATION
# ============================================================

def normalise_text(
    text: str | None,
) -> str:
    """
    Conservative OCR comparison normalisation.

    This does NOT translate or medically reinterpret text.
    """

    text = unicodedata.normalize(
        "NFKC",
        text or "",
    )

    text = text.casefold()

    # Preserve letters and numbers but normalise punctuation.
    text = re.sub(
        r"[^\w\s.]",
        " ",
        text,
        flags=re.UNICODE,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def normalise_field(
    value,
) -> str:

    if value is None:
        return ""

    return normalise_text(
        str(value)
    )


def extract_numbers(
    text: str | None,
) -> list[str]:

    values = re.findall(
        r"\b\d+(?:[.,]\d+)?\b",
        text or "",
    )

    return [
        value.replace(
            ",",
            ".",
        )
        for value in values
    ]


# ============================================================
# FUZZY TEXT RETENTION
# ============================================================

def fuzzy_contains(
    text: str,
    expected: str,
    threshold: float = 0.82,
) -> bool:

    text_norm = normalise_text(
        text
    )

    expected_norm = normalise_text(
        expected
    )

    if not expected_norm:
        return True

    if expected_norm in text_norm:
        return True

    text_tokens = (
        text_norm.split()
    )

    expected_tokens = (
        expected_norm.split()
    )

    if not text_tokens:
        return False

    width = max(
        1,
        len(
            expected_tokens
        ),
    )

    candidates = []

    for candidate_width in {
        max(
            1,
            width - 1,
        ),
        width,
        width + 1,
    }:

        for index in range(
            max(
                0,
                len(text_tokens)
                - candidate_width
                + 1,
            )
        ):

            candidates.append(
                " ".join(
                    text_tokens[
                        index:
                        index
                        + candidate_width
                    ]
                )
            )

    return any(
        SequenceMatcher(
            None,
            expected_norm,
            candidate,
        ).ratio()
        >= threshold
        for candidate
        in candidates
    )


# ============================================================
# DATA HELPERS
# ============================================================

def prescription_type(
    image: Path,
    fields: dict | None,
) -> str:

    if fields:

        declared = (
            fields.get(
                "prescription_type"
            )
            or fields.get(
                "type"
            )
        )

        if declared in {
            "printed",
            "handwritten",
        }:
            return declared

    stem = (
        image.stem.lower()
    )

    if stem.startswith(
        "handwritten"
    ):
        return "handwritten"

    if stem.startswith(
        "printed"
    ):
        return "printed"

    return "unspecified"


def load_fields(
    image: Path,
) -> dict | None:

    path = image.with_name(
        image.stem
        + ".fields.json"
    )

    if not path.exists():
        return None

    return json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )


def ground_truth_text_path(
    image: Path,
) -> Path:

    return image.with_suffix(
        ".txt"
    )


# ============================================================
# MEDICATION STRUCTURE NORMALISATION
# ============================================================

MEDICATION_LIST_KEYS = {
    "medications",
    "medicines",
    "drugs",
    "prescription",
    "prescriptions",
}


def find_medication_list(
    value,
) -> list[dict]:

    if isinstance(
        value,
        dict,
    ):

        for key, child in (
            value.items()
        ):

            if (
                key.lower()
                in MEDICATION_LIST_KEYS
                and isinstance(
                    child,
                    list,
                )
            ):

                dict_items = [
                    item
                    for item in child
                    if isinstance(
                        item,
                        dict,
                    )
                ]

                if dict_items:
                    return dict_items

        for child in (
            value.values()
        ):

            found = (
                find_medication_list(
                    child
                )
            )

            if found:
                return found

    elif isinstance(
        value,
        list,
    ):

        for child in value:

            found = (
                find_medication_list(
                    child
                )
            )

            if found:
                return found

    return []


FIELD_ALIASES = {
    "name": [
        "name",
        "medication_name",
        "medicine_name",
        "medicine",
        "drug",
        "generic_name",
    ],

    "strength": [
        "strength",
    ],

    "dose": [
        "dose",
        "dosage",
        "quantity",
    ],

    "frequency": [
        "frequency",
        "freq",
    ],

    "duration": [
        "duration",
    ],

    "instructions": [
        "instructions",
        "instruction",
        "timing",
        "directions",
        "advice",
    ],
}


def medication_field(
    medication: dict,
    field: str,
):

    for key in FIELD_ALIASES[
        field
    ]:

        if (
            key in medication
            and medication[
                key
            ] not in {
                None,
                "",
            }
        ):

            return medication[
                key
            ]

    return None


# ============================================================
# FIELD MATCHING
# ============================================================

def field_matches(
    expected,
    predicted,
    field: str,
) -> bool:

    exp = normalise_field(
        expected
    )

    pred = normalise_field(
        predicted
    )

    if not exp:
        return True

    if not pred:
        return False

    if exp == pred:
        return True

    if (
        exp in pred
        or pred in exp
    ):
        return True

    threshold = (
        0.80
        if field
        == "name"
        else 0.86
    )

    return (
        SequenceMatcher(
            None,
            exp,
            pred,
        ).ratio()
        >= threshold
    )


def medication_name_similarity(
    expected: dict,
    predicted: dict,
) -> float:

    exp = normalise_field(
        medication_field(
            expected,
            "name",
        )
    )

    pred = normalise_field(
        medication_field(
            predicted,
            "name",
        )
    )

    if not exp or not pred:
        return 0.0

    return SequenceMatcher(
        None,
        exp,
        pred,
    ).ratio()


def match_medications(
    expected: list[dict],
    predicted: list[dict],
) -> list[
    tuple[
        dict,
        dict | None,
    ]
]:

    remaining = (
        predicted.copy()
    )

    matched = []

    for expected_med in expected:

        if not remaining:

            matched.append(
                (
                    expected_med,
                    None,
                )
            )

            continue

        ranked = sorted(
            remaining,
            key=lambda pred:
                medication_name_similarity(
                    expected_med,
                    pred,
                ),
            reverse=True,
        )

        best = ranked[0]

        similarity = (
            medication_name_similarity(
                expected_med,
                best,
            )
        )

        if similarity >= 0.60:

            matched.append(
                (
                    expected_med,
                    best,
                )
            )

            remaining.remove(
                best
            )

        else:

            matched.append(
                (
                    expected_med,
                    None,
                )
            )

    return matched


# ============================================================
# STRUCTURED FIELD SCORING
# ============================================================

STRUCTURED_FIELDS = [
    "name",
    "strength",
    "dose",
    "frequency",
    "duration",
    "instructions",
]


def score_structured(
    expected_fields: dict,
    predicted_structure: dict,
) -> dict:

    expected_meds = (
        expected_fields.get(
            "medications"
        )
        or []
    )

    predicted_meds = (
        find_medication_list(
            predicted_structure
        )
    )

    pairs = match_medications(
        expected_meds,
        predicted_meds,
    )

    field_stats = {
        field: {
            "correct": 0,
            "total": 0,
        }
        for field
        in STRUCTURED_FIELDS
    }

    for expected_med, predicted_med in pairs:

        for field in (
            STRUCTURED_FIELDS
        ):

            expected_value = (
                medication_field(
                    expected_med,
                    field,
                )
            )

            if (
                expected_value
                in {
                    None,
                    "",
                }
            ):
                continue

            field_stats[
                field
            ][
                "total"
            ] += 1

            predicted_value = (
                medication_field(
                    predicted_med,
                    field,
                )
                if predicted_med
                else None
            )

            if field_matches(
                expected_value,
                predicted_value,
                field,
            ):

                field_stats[
                    field
                ][
                    "correct"
                ] += 1

    total_expected = sum(
        stat["total"]
        for stat in field_stats.values()
    )

    total_correct = sum(
        stat["correct"]
        for stat in field_stats.values()
    )

    result = {
        "expected_medications":
            len(
                expected_meds
            ),

        "predicted_medications":
            len(
                predicted_meds
            ),

        "fields":
            {},
    }

    for field, stat in (
        field_stats.items()
    ):

        result[
            "fields"
        ][
            field
        ] = {
            **stat,

            "accuracy":
                (
                    stat[
                        "correct"
                    ]
                    / stat[
                        "total"
                    ]
                    if stat[
                        "total"
                    ]
                    else None
                ),
        }

    result[
        "overall_correct"
    ] = total_correct

    result[
        "overall_total"
    ] = total_expected

    result[
        "overall_accuracy"
    ] = (
        total_correct
        / total_expected
        if total_expected
        else None
    )

    return result


# ============================================================
# METRIC HELPERS
# ============================================================

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

    return statistics.mean(
        values
    )


def rate_or_none(
    values,
):

    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return None

    return sum(
        bool(value)
        for value in values
    ) / len(values)


def round4(
    value,
):

    if value is None:
        return None

    return round(
        value,
        4,
    )


# ============================================================
# ARGUMENTS
# ============================================================

parser = argparse.ArgumentParser()

parser.add_argument(
    "--structured",
    action="store_true",
    help=(
        "Also run LLM-based structured "
        "prescription extraction."
    ),
)

args = parser.parse_args()


# ============================================================
# FIND IMAGES
# ============================================================

images = sorted(
    path
    for path
    in DATA_DIR.iterdir()
    if (
        path.is_file()
        and path.suffix.lower()
        in IMAGE_SUFFIXES
        and not path.name.endswith(
            ".pre.png"
        )
    )
)


print()
print(
    "=" * 82
)

print(
    "MediExplain+ Prescription OCR Evaluation"
)

print(
    "=" * 82
)


if not images:

    print()
    print(
        "OCR evaluation infrastructure is ready."
    )

    print(
        "No prescription test images "
        "have been added yet."
    )

    print()
    print(
        "Add images later to:"
    )

    print(
        f"  {DATA_DIR.relative_to(ROOT)}"
    )

    print()
    print(
        "Recommended final dataset:"
    )

    print(
        "  5 printed prescriptions"
    )

    print(
        "  5 handwritten prescriptions"
    )

    print()
    print(
        "Each image requires:"
    )

    print(
        "  <same-name>.txt"
        "          verified transcription"
    )

    print(
        "  <same-name>.fields.json"
        "  verified medication fields"
    )

    print()

    sys.exit(0)


# ============================================================
# RUN EVALUATION
# ============================================================

rows = []


for index, image in enumerate(
    images,
    start=1,
):

    gt_path = (
        ground_truth_text_path(
            image
        )
    )

    fields = load_fields(
        image
    )

    ptype = prescription_type(
        image,
        fields,
    )


    print()
    print(
        f"[{index}/{len(images)}] "
        f"{image.name} "
        f"({ptype})"
    )


    if not gt_path.exists():

        print(
            "  SKIPPED: missing ground-truth .txt"
        )

        continue


    reference = (
        gt_path
        .read_text(
            encoding="utf-8",
        )
        .strip()
    )


    result = (
        ocr_service
        .extract_text(
            image
        )
    )


    available = bool(
        result.get(
            "available"
        )
    )


    hypothesis = (
        result.get(
            "text"
        )
        or ""
    )


    if available:

        ref_norm = (
            normalise_text(
                reference
            )
        )

        hyp_norm = (
            normalise_text(
                hypothesis
            )
        )


        if ref_norm:

            image_wer = wer(
                ref_norm,
                hyp_norm,
            )

            image_cer = cer(
                ref_norm,
                hyp_norm,
            )

        else:

            image_wer = None
            image_cer = None

    else:

        image_wer = None
        image_cer = None


    # --------------------------------------------------------
    # NUMBER RETENTION
    # --------------------------------------------------------

    reference_numbers = (
        extract_numbers(
            reference
        )
    )

    hypothesis_numbers = (
        extract_numbers(
            hypothesis
        )
    )


    if reference_numbers:

        ref_counter = Counter(
            reference_numbers
        )

        hyp_counter = Counter(
            hypothesis_numbers
        )

        retained = sum(
            min(
                count,
                hyp_counter[
                    number
                ],
            )
            for number, count
            in ref_counter.items()
        )

        number_retention = (
            retained
            / sum(
                ref_counter.values()
            )
        )

    else:

        number_retention = None


    # --------------------------------------------------------
    # MEDICINE-NAME RETENTION
    # --------------------------------------------------------

    medication_retention = None

    expected_medications = []

    if fields:

        expected_medications = (
            fields.get(
                "medications"
            )
            or []
        )


    expected_names = [
        medication_field(
            medication,
            "name",
        )
        for medication
        in expected_medications
    ]

    expected_names = [
        name
        for name in expected_names
        if name
    ]


    if expected_names:

        medication_retention = (
            sum(
                fuzzy_contains(
                    hypothesis,
                    name,
                )
                for name
                in expected_names
            )
            / len(
                expected_names
            )
        )


    # --------------------------------------------------------
    # OPTIONAL STRUCTURED EVALUATION
    # --------------------------------------------------------

    predicted_structure = None
    structured_score = None
    structured_error = None


    if (
        args.structured
        and available
        and hypothesis.strip()
        and fields
    ):

        try:

            predicted_structure = (
                asyncio.run(
                    ocr_service
                    .structure_ocr_text(
                        hypothesis
                    )
                )
            )

            structured_score = (
                score_structured(
                    fields,
                    predicted_structure
                    or {},
                )
            )

        except Exception as exc:

            structured_error = str(
                exc
            )


    row = {
        "image":
            image.name,

        "type":
            ptype,

        "available":
            available,

        "engine":
            result.get(
                "engine"
            ),

        "confidence":
            result.get(
                "confidence"
            ),

        "warning":
            result.get(
                "warning"
            ),

        "wer":
            image_wer,

        "cer":
            image_cer,

        "number_retention":
            number_retention,

        "medication_name_retention":
            medication_retention,

        "reference":
            reference,

        "hypothesis":
            hypothesis,

        "structured_enabled":
            args.structured,

        "structured":
            predicted_structure,

        "structured_score":
            structured_score,

        "structured_error":
            structured_error,
    }


    rows.append(
        row
    )


    print(
        f"  engine:     "
        f"{row['engine']}"
    )

    print(
        f"  confidence: "
        f"{row['confidence']}"
    )

    if image_wer is not None:

        print(
            f"  WER:        "
            f"{image_wer * 100:.1f}%"
        )

    if image_cer is not None:

        print(
            f"  CER:        "
            f"{image_cer * 100:.1f}%"
        )

    if number_retention is not None:

        print(
            f"  numbers:    "
            f"{number_retention * 100:.1f}%"
        )

    if medication_retention is not None:

        print(
            f"  medicines:  "
            f"{medication_retention * 100:.1f}%"
        )


# ============================================================
# AGGREGATION
# ============================================================

def aggregate(
    subset: list[dict],
) -> dict:

    if not subset:
        return {
            "n": 0,
        }

    available = [
        row
        for row in subset
        if row[
            "available"
        ]
    ]

    references = [
        normalise_text(
            row[
                "reference"
            ]
        )
        for row
        in available
    ]

    hypotheses = [
        normalise_text(
            row[
                "hypothesis"
            ]
        )
        for row
        in available
    ]


    if references:

        corpus_reference = (
            " ".join(
                references
            )
        )

        corpus_hypothesis = (
            " ".join(
                hypotheses
            )
        )

        corpus_wer = wer(
            corpus_reference,
            corpus_hypothesis,
        )

        corpus_cer = cer(
            corpus_reference,
            corpus_hypothesis,
        )

    else:

        corpus_wer = None
        corpus_cer = None


    engine_counts = dict(
        Counter(
            row[
                "engine"
            ]
            for row
            in available
            if row[
                "engine"
            ]
        )
    )


    result = {
        "n":
            len(
                subset
            ),

        "available":
            len(
                available
            ),

        "availability_rate":
            round4(
                len(
                    available
                )
                / len(
                    subset
                )
            ),

        "corpus_wer":
            round4(
                corpus_wer
            ),

        "corpus_cer":
            round4(
                corpus_cer
            ),

        "mean_image_wer":
            round4(
                mean_or_none(
                    row[
                        "wer"
                    ]
                    for row
                    in available
                )
            ),

        "mean_image_cer":
            round4(
                mean_or_none(
                    row[
                        "cer"
                    ]
                    for row
                    in available
                )
            ),

        "mean_confidence":
            round4(
                mean_or_none(
                    row[
                        "confidence"
                    ]
                    for row
                    in available
                )
            ),

        "low_confidence_warning_rate":
            round4(
                rate_or_none(
                    bool(
                        row[
                            "warning"
                        ]
                    )
                    for row
                    in available
                )
            ),

        "number_retention_rate":
            round4(
                mean_or_none(
                    row[
                        "number_retention"
                    ]
                    for row
                    in available
                )
            ),

        "medication_name_retention_rate":
            round4(
                mean_or_none(
                    row[
                        "medication_name_retention"
                    ]
                    for row
                    in available
                )
            ),

        "engine_counts":
            engine_counts,
    }


    # --------------------------------------------------------
    # STRUCTURED RESULTS
    # --------------------------------------------------------

    structured_rows = [
        row
        for row in subset
        if row.get(
            "structured_score"
        )
    ]


    if structured_rows:

        field_results = {}

        for field in (
            STRUCTURED_FIELDS
        ):

            correct = sum(
                row[
                    "structured_score"
                ][
                    "fields"
                ][
                    field
                ][
                    "correct"
                ]
                for row
                in structured_rows
            )

            total = sum(
                row[
                    "structured_score"
                ][
                    "fields"
                ][
                    field
                ][
                    "total"
                ]
                for row
                in structured_rows
            )

            field_results[
                field
            ] = {
                "correct":
                    correct,

                "total":
                    total,

                "accuracy":
                    round4(
                        correct / total
                    )
                    if total
                    else None,
            }


        overall_correct = sum(
            row[
                "structured_score"
            ][
                "overall_correct"
            ]
            for row
            in structured_rows
        )

        overall_total = sum(
            row[
                "structured_score"
            ][
                "overall_total"
            ]
            for row
            in structured_rows
        )


        result[
            "structured"
        ] = {
            "n":
                len(
                    structured_rows
                ),

            "fields":
                field_results,

            "overall_correct":
                overall_correct,

            "overall_total":
                overall_total,

            "overall_field_accuracy":
                round4(
                    overall_correct
                    / overall_total
                )
                if overall_total
                else None,
        }


    return result


printed_rows = [
    row
    for row in rows
    if row[
        "type"
    ]
    == "printed"
]

handwritten_rows = [
    row
    for row in rows
    if row[
        "type"
    ]
    == "handwritten"
]


summary = {
    "overall":
        aggregate(
            rows
        ),

    "printed":
        aggregate(
            printed_rows
        ),

    "handwritten":
        aggregate(
            handwritten_rows
        ),
}


# ============================================================
# JSON OUTPUT
# ============================================================

result = {
    "evaluation":
        "prescription_ocr",

    "structured_evaluation_enabled":
        args.structured,

    "summary":
        summary,

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
# CSV OUTPUT
# ============================================================

CSV_FIELDS = [
    "image",
    "type",
    "available",
    "engine",
    "confidence",
    "warning",
    "wer",
    "cer",
    "number_retention",
    "medication_name_retention",
    "structured_error",
    "reference",
    "hypothesis",
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

        writer.writerow(
            {
                field:
                    row.get(
                        field
                    )
                for field
                in CSV_FIELDS
            }
        )


# ============================================================
# CONSOLE SUMMARY
# ============================================================

print()
print(
    "=" * 82
)

print(
    "FINAL OCR SUMMARY"
)

print(
    "=" * 82
)


for name in (
    "overall",
    "printed",
    "handwritten",
):

    metrics = (
        summary[
            name
        ]
    )


    print()
    print(
        name.upper()
    )

    print(
        "-" * 45
    )

    print(
        f"Images:                 "
        f"{metrics.get('n', 0)}"
    )

    if (
        metrics.get(
            "n",
            0,
        )
        == 0
    ):
        continue


    def show_pct(
        label,
        value,
    ):

        if value is None:
            print(
                f"{label:<24}"
                "n/a"
            )

        else:
            print(
                f"{label:<24}"
                f"{value * 100:.1f}%"
            )


    show_pct(
        "OCR availability:",
        metrics.get(
            "availability_rate"
        ),
    )

    show_pct(
        "Corpus WER:",
        metrics.get(
            "corpus_wer"
        ),
    )

    show_pct(
        "Corpus CER:",
        metrics.get(
            "corpus_cer"
        ),
    )

    show_pct(
        "Number retention:",
        metrics.get(
            "number_retention_rate"
        ),
    )

    show_pct(
        "Medicine retention:",
        metrics.get(
            "medication_name_retention_rate"
        ),
    )


    confidence = metrics.get(
        "mean_confidence"
    )

    if confidence is not None:

        print(
            f"{'Mean OCR confidence:':<24}"
            f"{confidence * 100:.1f}%"
        )


    if metrics.get(
        "structured"
    ):

        show_pct(
            "Structured accuracy:",
            metrics[
                "structured"
            ][
                "overall_field_accuracy"
            ],
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