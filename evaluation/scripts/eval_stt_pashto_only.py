"""
MediExplain+ final Speech-to-Text evaluation.

Measures:
- Word Error Rate (WER)
- Character Error Rate (CER)
- Medicine-name retention
- Critical-number/dose retention
- Code-switch English retention
- Per-language and overall results

Test data structure
-------------------

For every audio file:

    sample01.wav
    sample01.txt
    sample01.lang

Optional:

    sample01.group
    sample01.meds
    sample01.condition

Example:

    sample01.lang
        ur

    sample01.group
        ur_en

    sample01.meds
        Panadol
        Augmentin

    sample01.condition
        quiet_laptop_mic

Supported final product language codes:

    en
    ur
    pa_shah
    ps
    sd
    ar

Recommended reporting groups:

    en
    ur
    pa_shah
    ps
    sd
    ar
    ur_en
    pa_shah_en

Run:

    python evaluation/scripts/eval_stt.py

Outputs:

    evaluation/results/stt_detailed_results.csv
    evaluation/results/stt_language_summary.csv
    evaluation/results/stt_evaluation.json
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
import unicodedata

from collections import defaultdict
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

BACKEND = ROOT / "backend"

sys.path.insert(
    0,
    str(BACKEND),
)

AUDIO_DIR = (
    ROOT
    / "evaluation"
    / "data"
    / "stt_audio_pashto_only"
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
    / "stt_pashto_evaluation.json"
)

DETAIL_OUT = (
    RESULTS_DIR
    / "stt_pashto_detailed_results.csv"
)

SUMMARY_OUT = (
    RESULTS_DIR
    / "stt_pashto_language_summary.csv"
)


# ============================================================
# DEPENDENCIES
# ============================================================

try:
    from jiwer import (
        cer,
        wer,
    )

except ImportError:
    print(
        "\nMissing dependency: jiwer\n"
        "\nInstall with:\n"
        "    pip install jiwer\n",
        file=sys.stderr,
    )

    sys.exit(1)


from app.services import stt as stt_svc


# ============================================================
# CONSTANTS
# ============================================================

AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".webm",
    ".mp4",
}


FINAL_LANGUAGE_CODES = {
    "en",
    "ur",
    "pa_shah",
    "ps",
    "sd",
    "ar",
}


GROUP_LABELS = {
    "en": "English",
    "ur": "Urdu",
    "pa_shah": "Punjabi Shahmukhi",
    "ps": "Pashto",
    "sd": "Sindhi",
    "ar": "Arabic",
    "ur_en": "Urdu-English",
    "pa_shah_en": "Punjabi-English",
}


# English tokens commonly appearing in consultations.
# Used only for code-switch retention measurement.
LATIN_WORD_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9'-]*\b"
)


# Numbers including:
# 500
# 5.5
# 500mg
# 2ml
NUMBER_RE = re.compile(
    r"\b\d+(?:\.\d+)?(?:\s*(?:mg|mcg|g|ml|iu|units?))?\b",
    re.I,
)


# Urdu / Arabic-script digits → ASCII digits.
DIGIT_TRANSLATION = str.maketrans(
    {
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",

        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }
)


# ============================================================
# NORMALISATION
# ============================================================

def normalise_text(
    text: str | None,
) -> str:
    """
    Conservative multilingual scoring normalisation.

    Important:
    - does NOT transliterate scripts;
    - does NOT translate text;
    - preserves Urdu/Punjabi/Pashto/Sindhi/Arabic;
    - preserves English words in code-switched consultations;
    - removes punctuation differences that should not count as STT errors.
    """

    text = unicodedata.normalize(
        "NFKC",
        text or "",
    )

    text = text.translate(
        DIGIT_TRANSLATION
    )

    text = text.casefold()

    cleaned = []

    for char in text:
        category = unicodedata.category(
            char
        )

        # Replace punctuation/symbols with spaces.
        if (
            category.startswith("P")
            or category.startswith("S")
        ):
            cleaned.append(" ")

        else:
            cleaned.append(char)

    text = "".join(
        cleaned
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# SIDE-CAR FILE HELPERS
# ============================================================

def read_optional_text(
    path: Path,
) -> str | None:
    if not path.exists():
        return None

    value = path.read_text(
        encoding="utf-8",
    ).strip()

    return value or None


def read_medical_terms(
    audio_path: Path,
) -> list[str]:
    """
    Optional <sample>.meds file.

    Put one expected medication/medical term per line.

    Example:

        Panadol
        Augmentin
        metformin
    """

    path = audio_path.with_suffix(
        ".meds"
    )

    if not path.exists():
        return []

    terms = []

    for line in path.read_text(
        encoding="utf-8",
    ).splitlines():

        line = line.strip()

        if line:
            terms.append(line)

    return terms


# ============================================================
# RETENTION METRICS
# ============================================================

def phrase_present(
    phrase: str,
    hypothesis: str,
) -> bool:

    phrase_norm = normalise_text(
        phrase
    )

    hyp_norm = normalise_text(
        hypothesis
    )

    if not phrase_norm:
        return False

    def contains_arabic_script(
        value: str,
    ) -> bool:
        for char in value:
            code = ord(char)

            if (
                0x0600 <= code <= 0x06FF
                or 0x0750 <= code <= 0x077F
                or 0x08A0 <= code <= 0x08FF
                or 0xFB50 <= code <= 0xFDFF
                or 0xFE70 <= code <= 0xFEFF
            ):
                return True

        return False

    # For Arabic-derived medicine names only,
    # ignore harmless internal whitespace:
    #
    # میٹفارمن
    # میٹ فارمن
    #
    # This does NOT fuzzy-match different spellings.
    if contains_arabic_script(
        phrase_norm
    ):
        phrase_compact = re.sub(
            r"\s+",
            "",
            phrase_norm,
        )

        hyp_compact = re.sub(
            r"\s+",
            "",
            hyp_norm,
        )

        return (
            phrase_compact
            in hyp_compact
        )

    return (
        phrase_norm
        in hyp_norm
    )


def medicine_retention(
    expected_terms: list[str],
    hypothesis: str,
) -> dict:
    """
    Percentage of manually-labelled important
    medicine/medical terms retained by STT.
    """

    if not expected_terms:
        return {
            "expected": 0,
            "retained": 0,
            "rate": None,
            "missing": [],
        }

    missing = []

    retained = 0

    for term in expected_terms:
        if phrase_present(
            term,
            hypothesis,
        ):
            retained += 1

        else:
            missing.append(
                term
            )

    return {
        "expected":
            len(expected_terms),

        "retained":
            retained,

        "rate":
            retained
            / len(expected_terms),

        "missing":
            missing,
    }


def extract_numbers(
    text: str,
) -> list[str]:
    """
    Extract and canonicalise critical numeric dose values.

    Examples normalised to the same representation:

        500 mg
        500mg
        500 ملی گرام
        500 میلی گرام

        -> 500mg

    This does not convert spoken number words such as
    'پنج سو' into digits, avoiding post-hoc language-specific
    inflation of evaluation scores.
    """

    normalised = normalise_text(
        text
    )

    dose_re = re.compile(
        r"(?<!\w)"
        r"(\d+(?:\.\d+)?)"
        r"\s*"
        r"("
        r"mcg|micrograms?|"
        r"mg|milligrams?|"
        r"ml|millilit(?:er|re)s?|"
        r"iu|units?|"
        r"میلی\s*گرام|"
        r"ملی\s*گرام|"
        r"ملي\s*غرام|"
        r"مائیکرو\s*گرام|"
        r"ميكرو\s*غرام|"
        r"میلی\s*لیٹر|"
        r"ملی\s*لیٹر|"
        r"ملي\s*لتر|"
        r"گرام|غرام|"
        r"g"
        r")?",
        re.I,
    )

    def canonical_unit(
        unit: str | None,
    ) -> str:

        if not unit:
            return ""

        compact = re.sub(
            r"\s+",
            "",
            unit.casefold(),
        )

        if compact in {
            "mg",
            "milligram",
            "milligrams",
            "میلیگرام",
            "ملیگرام",
            "مليغرام",
        }:
            return "mg"

        if compact in {
            "mcg",
            "microgram",
            "micrograms",
            "مائیکروگرام",
            "ميكروغرام",
        }:
            return "mcg"

        if compact in {
            "ml",
            "milliliter",
            "milliliters",
            "millilitre",
            "millilitres",
            "میلیلیٹر",
            "ملیلیٹر",
            "مليلتر",
        }:
            return "ml"

        if compact in {
            "g",
            "gram",
            "grams",
            "گرام",
            "غرام",
        }:
            return "g"

        if compact in {
            "iu",
            "unit",
            "units",
        }:
            return "iu"

        return compact

    values = []

    for match in dose_re.finditer(
        normalised
    ):
        number = match.group(1)
        unit = canonical_unit(
            match.group(2)
        )

        values.append(
            f"{number}{unit}"
        )

    return values


def number_retention(
    reference: str,
    hypothesis: str,
) -> dict:
    """
    Measures preservation of dose/number strings.

    Example:
        500 mg
        2
        5 days
    """

    expected = extract_numbers(
        reference
    )

    found = extract_numbers(
        hypothesis
    )

    if not expected:
        return {
            "expected": 0,
            "retained": 0,
            "rate": None,
            "missing": [],
        }

    remaining = list(
        found
    )

    retained = 0
    missing = []

    for number in expected:
        if number in remaining:
            retained += 1

            remaining.remove(
                number
            )

        else:
            missing.append(
                number
            )

    return {
        "expected":
            len(expected),

        "retained":
            retained,

        "rate":
            retained
            / len(expected),

        "missing":
            missing,
    }


def english_code_switch_retention(
    reference: str,
    hypothesis: str,
) -> dict:
    """
    Measures how many Latin/English tokens in a mixed-language
    reference are retained in the STT output.

    This directly tests the earlier failure mode where English
    words disappeared from Urdu/Punjabi mixed speech.
    """

    ref_words = [
        word.casefold()
        for word
        in LATIN_WORD_RE.findall(
            reference
        )
    ]

    hyp_words = [
        word.casefold()
        for word
        in LATIN_WORD_RE.findall(
            hypothesis
        )
    ]

    if not ref_words:
        return {
            "expected": 0,
            "retained": 0,
            "rate": None,
            "missing": [],
        }

    remaining = list(
        hyp_words
    )

    retained = 0
    missing = []

    for word in ref_words:
        if word in remaining:
            retained += 1

            remaining.remove(
                word
            )

        else:
            missing.append(
                word
            )

    return {
        "expected":
            len(ref_words),

        "retained":
            retained,

        "rate":
            retained
            / len(ref_words),

        "missing":
            missing,
    }


# ============================================================
# SCRIPT + LOW-CONFIDENCE SAFETY METRICS
# ============================================================

DEVANAGARI_RE = re.compile(
    r"[\u0900-\u097F]"
)

GURMUKHI_RE = re.compile(
    r"[\u0A00-\u0A7F]"
)

ARABIC_SCRIPT_RE = re.compile(
    r"[\u0600-\u06FF"
    r"\u0750-\u077F"
    r"\u08A0-\u08FF"
    r"\uFB50-\uFDFF"
    r"\uFE70-\uFEFF]"
)

ARABIC_SCRIPT_LANGUAGES = {
    "ur",
    "pa_shah",
    "ps",
    "sd",
    "ar",
}


def script_correctness(
    expected_language: str | None,
    hypothesis: str,
) -> dict:
    """
    Validate the script exposed by STT.

    For Urdu, Punjabi Shahmukhi, Pashto,
    Sindhi and Arabic:
      - Devanagari must not appear
      - Gurmukhi must not appear
      - Arabic-derived script should be present

    English should retain Latin text.

    Mixed-language samples use their primary
    expected language plus the separate English
    code-switch retention metric.
    """

    hypothesis = hypothesis or ""

    devanagari = bool(
        DEVANAGARI_RE.search(
            hypothesis
        )
    )

    gurmukhi = bool(
        GURMUKHI_RE.search(
            hypothesis
        )
    )

    arabic_script = bool(
        ARABIC_SCRIPT_RE.search(
            hypothesis
        )
    )

    latin = bool(
        LATIN_WORD_RE.search(
            hypothesis
        )
    )

    forbidden = []

    if devanagari:
        forbidden.append(
            "Devanagari"
        )

    if gurmukhi:
        forbidden.append(
            "Gurmukhi"
        )

    if (
        expected_language
        in ARABIC_SCRIPT_LANGUAGES
    ):
        valid = (
            bool(hypothesis.strip())
            and arabic_script
            and not forbidden
        )

    elif (
        expected_language
        == "en"
    ):
        valid = (
            bool(hypothesis.strip())
            and latin
            and not forbidden
        )

    else:
        valid = (
            bool(hypothesis.strip())
            and not forbidden
        )

    return {
        "valid": bool(valid),
        "forbidden_scripts":
            forbidden,
        "arabic_script_present":
            arabic_script,
        "latin_present":
            latin,
    }


def low_confidence_review_metrics(
    output: dict,
    threshold: float = 0.70,
) -> dict:
    """
    Verify that segments below the deployed
    confidence threshold are flagged for
    clinician review.
    """

    segments = (
        output.get(
            "segments"
        )
        or []
    )

    low_confidence = []

    total_review_required = 0

    for segment in segments:

        if segment.get(
            "needs_review"
        ):
            total_review_required += 1

        confidence = segment.get(
            "confidence"
        )

        try:
            confidence = (
                float(confidence)
                if confidence
                is not None
                else None
            )
        except Exception:
            confidence = None

        if (
            confidence is not None
            and confidence < threshold
        ):
            low_confidence.append(
                segment
            )

    flagged = sum(
        1
        for segment
        in low_confidence
        if bool(
            segment.get(
                "needs_review"
            )
        )
    )

    count = len(
        low_confidence
    )

    return {
        "segments_total":
            len(segments),

        "low_confidence_segments":
            count,

        "low_confidence_flagged":
            flagged,

        "review_recall":
            (
                flagged / count
                if count
                else None
            ),

        "review_gate_pass":
            (
                flagged == count
            ),

        "segments_requiring_review":
            total_review_required,
    }


# ============================================================
# STATISTICS
# ============================================================

def metric_stats(
    values: list[float],
) -> dict | None:

    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return None

    return {
        "n":
            len(values),

        "mean":
            round(
                statistics.mean(
                    values
                ),
                4,
            ),

        "median":
            round(
                statistics.median(
                    values
                ),
                4,
            ),

        "min":
            round(
                min(values),
                4,
            ),

        "max":
            round(
                max(values),
                4,
            ),
    }


def percent(
    value: float | None,
) -> str:
    if value is None:
        return "n/a"

    return (
        f"{value * 100:.1f}%"
    )


# ============================================================
# DISCOVER AUDIO
# ============================================================

if not AUDIO_DIR.exists():
    print(
        "\nSTT evaluation data folder does not exist.\n"
        f"\nCreate:\n    {AUDIO_DIR}\n"
    )

    sys.exit(1)


audio_files = sorted(
    path
    for path in AUDIO_DIR.iterdir()
    if (
        path.is_file()
        and path.suffix.lower()
        in AUDIO_EXTENSIONS
    )
)


if not audio_files:
    print(
        "\nNo STT test audio found.\n"
        f"\nAdd labelled audio to:\n"
        f"    {AUDIO_DIR}\n"
    )

    sys.exit(1)


# ============================================================
# RUN EVALUATION
# ============================================================

print()
print(
    "=" * 92
)

print(
    "MediExplain+ Final STT Evaluation"
)

print(
    "=" * 92
)


results = []


for audio_path in audio_files:

    reference_path = (
        audio_path.with_suffix(
            ".txt"
        )
    )

    language_path = (
        audio_path.with_suffix(
            ".lang"
        )
    )

    group_path = (
        audio_path.with_suffix(
            ".group"
        )
    )

    condition_path = (
        audio_path.with_suffix(
            ".condition"
        )
    )


    # --------------------------------------------------------
    # REQUIRED REFERENCE
    # --------------------------------------------------------

    if not reference_path.exists():
        print(
            f"SKIP {audio_path.name}: "
            "missing reference transcript."
        )

        continue


    reference = (
        reference_path
        .read_text(
            encoding="utf-8"
        )
        .strip()
    )


    if not reference:
        print(
            f"SKIP {audio_path.name}: "
            "reference transcript is empty."
        )

        continue


    # --------------------------------------------------------
    # LANGUAGE
    # --------------------------------------------------------

    expected_language = (
        read_optional_text(
            language_path
        )
    )


    if (
        expected_language
        and expected_language
        not in FINAL_LANGUAGE_CODES
    ):
        print(
            f"SKIP {audio_path.name}: "
            f"unsupported .lang value "
            f"{expected_language!r}"
        )

        continue


    group = (
        read_optional_text(
            group_path
        )
        or expected_language
        or "unknown"
    )


    condition = (
        read_optional_text(
            condition_path
        )
        or "unspecified"
    )


    expected_meds = (
        read_medical_terms(
            audio_path
        )
    )


    # --------------------------------------------------------
    # TRANSCRIBE
    # --------------------------------------------------------

    print(
        f"\nTranscribing: "
        f"{audio_path.name}"
    )

    print(
        f"  language hint: "
        f"{expected_language or 'auto'}"
    )

    print(
        f"  report group: "
        f"{group}"
    )


    try:
        # Mixed-language samples must use the same automatic
        # acoustic language-detection path as the deployed
        # consultation workflow. Passing primary_language="ur"
        # or "pa_shah" forces Whisper into a single-language
        # transcription and disables segment-level code-switch
        # detection.
        if group in {
            "ur_en",
            "pa_shah_en",
        }:
            output = (
                stt_svc.transcribe(
                    audio_path,
                    primary_language=None,
                    secondary_language="en",
                )
            )

        else:
            output = (
                stt_svc.transcribe(
                    audio_path,
                    primary_language=
                        expected_language,
                )
            )

    except Exception as exc:
        print(
            f"  FAILED: {exc}"
        )

        results.append(
            {
                "file":
                    audio_path.name,

                "group":
                    group,

                "expected_language":
                    expected_language,

                "condition":
                    condition,

                "error":
                    str(exc),
            }
        )

        continue


    hypothesis = (
        output.get(
            "text"
        )
        or ""
    ).strip()


    reference_normalised = (
        normalise_text(
            reference
        )
    )

    hypothesis_normalised = (
        normalise_text(
            hypothesis
        )
    )


    # --------------------------------------------------------
    # WER / CER
    # --------------------------------------------------------

    if (
        reference_normalised
        and hypothesis_normalised
    ):
        wer_score = wer(
            reference_normalised,
            hypothesis_normalised,
        )

        cer_score = cer(
            reference_normalised,
            hypothesis_normalised,
        )

    elif reference_normalised:
        wer_score = 1.0
        cer_score = 1.0

    else:
        wer_score = None
        cer_score = None


    # --------------------------------------------------------
    # RETENTION
    # --------------------------------------------------------

    med_result = (
        medicine_retention(
            expected_meds,
            hypothesis,
        )
    )


    number_result = (
        number_retention(
            reference,
            hypothesis,
        )
    )


    if group in {
        "ur_en",
        "pa_shah_en",
    }:
        code_switch_result = (
            english_code_switch_retention(
                reference,
                hypothesis,
            )
        )

    else:
        code_switch_result = {
            "expected": 0,
            "retained": 0,
            "rate": None,
            "missing": [],
        }


    # --------------------------------------------------------
    # SCRIPT / REVIEW-GATE SAFETY
    # --------------------------------------------------------

    script_result = (
        script_correctness(
            expected_language,
            hypothesis,
        )
    )

    review_result = (
        low_confidence_review_metrics(
            output,
            threshold=0.70,
        )
    )



    # --------------------------------------------------------
    # SAVE SAMPLE
    # --------------------------------------------------------

    result = {
        "file":
            audio_path.name,

        "group":
            group,

        "condition":
            condition,

        "expected_language":
            expected_language,

        "detected_language":
            output.get(
                "language"
            ),

        "language_confidence":
            output.get(
                "language_confidence"
            ),

        "languages_detected":
            output.get(
                "languages_detected",
                [],
            ),

        "code_switched":
            output.get(
                "code_switched"
            ),

        "duration_seconds":
            output.get(
                "duration"
            ),

        "reference_words":
            len(
                reference_normalised.split()
            ),

        "hypothesis_words":
            len(
                hypothesis_normalised.split()
            ),

        "wer":
            round(
                wer_score,
                4,
            )
            if wer_score
            is not None
            else None,

        "cer":
            round(
                cer_score,
                4,
            )
            if cer_score
            is not None
            else None,

        "medicine_terms_expected":
            med_result[
                "expected"
            ],

        "medicine_terms_retained":
            med_result[
                "retained"
            ],

        "medicine_retention":
            round(
                med_result[
                    "rate"
                ],
                4,
            )
            if med_result[
                "rate"
            ]
            is not None
            else None,

        "missing_medicine_terms":
            med_result[
                "missing"
            ],

        "numbers_expected":
            number_result[
                "expected"
            ],

        "numbers_retained":
            number_result[
                "retained"
            ],

        "number_retention":
            round(
                number_result[
                    "rate"
                ],
                4,
            )
            if number_result[
                "rate"
            ]
            is not None
            else None,

        "missing_numbers":
            number_result[
                "missing"
            ],

        "english_tokens_expected":
            code_switch_result[
                "expected"
            ],

        "english_tokens_retained":
            code_switch_result[
                "retained"
            ],

        "code_switch_retention":
            round(
                code_switch_result[
                    "rate"
                ],
                4,
            )
            if code_switch_result[
                "rate"
            ]
            is not None
            else None,

        "missing_english_tokens":
            code_switch_result[
                "missing"
            ],

        "script_valid":
            script_result[
                "valid"
            ],

        "forbidden_scripts":
            script_result[
                "forbidden_scripts"
            ],

        "arabic_script_present":
            script_result[
                "arabic_script_present"
            ],

        "latin_present":
            script_result[
                "latin_present"
            ],

        "segments_total":
            review_result[
                "segments_total"
            ],

        "low_confidence_segments":
            review_result[
                "low_confidence_segments"
            ],

        "low_confidence_flagged_for_review":
            review_result[
                "low_confidence_flagged"
            ],

        "low_confidence_review_recall":
            round(
                review_result[
                    "review_recall"
                ],
                4,
            )
            if review_result[
                "review_recall"
            ]
            is not None
            else None,

        "review_gate_pass":
            review_result[
                "review_gate_pass"
            ],

        "segments_requiring_review":
            review_result[
                "segments_requiring_review"
            ],

        "reference":
            reference,

        "hypothesis":
            hypothesis,

        "error":
            None,
    }


    results.append(
        result
    )


    print(
        f"  WER: "
        f"{percent(wer_score)}"
    )

    print(
        f"  CER: "
        f"{percent(cer_score)}"
    )

    print(
        f"  medicine retention: "
        f"{percent(med_result['rate'])}"
    )

    print(
        f"  number retention: "
        f"{percent(number_result['rate'])}"
    )

    if (
        code_switch_result[
            "rate"
        ]
        is not None
    ):
        print(
            "  English code-switch "
            f"retention: "
            f"{percent(code_switch_result['rate'])}"
        )


# ============================================================
# VALID RESULTS ONLY
# ============================================================

valid_results = [
    result
    for result in results
    if not result.get(
        "error"
    )
]


if not valid_results:
    print(
        "\nNo valid STT evaluation "
        "samples completed."
    )

    sys.exit(1)


# ============================================================
# GROUP RESULTS
# ============================================================

by_group = defaultdict(
    list
)


for result in valid_results:
    by_group[
        result["group"]
    ].append(
        result
    )


summary = {}


for group, items in sorted(
    by_group.items()
):

    total_reference_words = sum(
        item[
            "reference_words"
        ]
        for item in items
    )


    medicine_expected = sum(
        item[
            "medicine_terms_expected"
        ]
        for item in items
    )

    medicine_retained = sum(
        item[
            "medicine_terms_retained"
        ]
        for item in items
    )


    numbers_expected = sum(
        item[
            "numbers_expected"
        ]
        for item in items
    )

    numbers_retained = sum(
        item[
            "numbers_retained"
        ]
        for item in items
    )


    english_expected = sum(
        item[
            "english_tokens_expected"
        ]
        for item in items
    )

    english_retained = sum(
        item[
            "english_tokens_retained"
        ]
        for item in items
    )


    summary[group] = {
        "label":
            GROUP_LABELS.get(
                group,
                group,
            ),

        "samples":
            len(items),

        "reference_words":
            total_reference_words,

        "wer":
            metric_stats(
                [
                    item["wer"]
                    for item in items
                    if item["wer"]
                    is not None
                ]
            ),

        "cer":
            metric_stats(
                [
                    item["cer"]
                    for item in items
                    if item["cer"]
                    is not None
                ]
            ),

        "medicine_retention":
            (
                medicine_retained
                / medicine_expected
            )
            if medicine_expected
            else None,

        "number_retention":
            (
                numbers_retained
                / numbers_expected
            )
            if numbers_expected
            else None,

        "code_switch_retention":
            (
                english_retained
                / english_expected
            )
            if english_expected
            else None,
    }


# ============================================================
# OVERALL
# ============================================================

overall = {
    "samples":
        len(valid_results),

    "reference_words":
        sum(
            item[
                "reference_words"
            ]
            for item
            in valid_results
        ),

    "wer":
        metric_stats(
            [
                item["wer"]
                for item
                in valid_results
                if item["wer"]
                is not None
            ]
        ),

    "cer":
        metric_stats(
            [
                item["cer"]
                for item
                in valid_results
                if item["cer"]
                is not None
            ]
        ),
}


# ============================================================
# WRITE DETAILED CSV
# ============================================================

detail_fields = [
    "file",
    "group",
    "condition",
    "expected_language",
    "detected_language",
    "language_confidence",
    "duration_seconds",
    "reference_words",
    "hypothesis_words",
    "wer",
    "cer",
    "medicine_terms_expected",
    "medicine_terms_retained",
    "medicine_retention",
    "numbers_expected",
    "numbers_retained",
    "number_retention",
    "english_tokens_expected",
    "english_tokens_retained",
    "code_switch_retention",
    "code_switched",
    "languages_detected",
    "missing_medicine_terms",
    "missing_numbers",
    "missing_english_tokens",
    "reference",
    "hypothesis",
    "error",
]


with DETAIL_OUT.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:

    writer = csv.DictWriter(
        handle,
        fieldnames=
            detail_fields,
    )

    writer.writeheader()

    for result in results:
        row = {
            field:
                result.get(
                    field
                )
            for field
            in detail_fields
        }

        for field in (
            "languages_detected",
            "missing_medicine_terms",
            "missing_numbers",
            "missing_english_tokens",
        ):
            if isinstance(
                row.get(field),
                list,
            ):
                row[field] = (
                    " | ".join(
                        str(x)
                        for x
                        in row[field]
                    )
                )

        writer.writerow(
            row
        )


# ============================================================
# WRITE SUMMARY CSV
# ============================================================

with SUMMARY_OUT.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:

    fields = [
        "group",
        "language",
        "samples",
        "reference_words",
        "mean_wer",
        "median_wer",
        "mean_cer",
        "medicine_retention",
        "number_retention",
        "code_switch_retention",
    ]

    writer = csv.DictWriter(
        handle,
        fieldnames=fields,
    )

    writer.writeheader()


    for group, data in summary.items():

        writer.writerow(
            {
                "group":
                    group,

                "language":
                    data["label"],

                "samples":
                    data["samples"],

                "reference_words":
                    data[
                        "reference_words"
                    ],

                "mean_wer":
                    (
                        data["wer"][
                            "mean"
                        ]
                        if data["wer"]
                        else None
                    ),

                "median_wer":
                    (
                        data["wer"][
                            "median"
                        ]
                        if data["wer"]
                        else None
                    ),

                "mean_cer":
                    (
                        data["cer"][
                            "mean"
                        ]
                        if data["cer"]
                        else None
                    ),

                "medicine_retention":
                    data[
                        "medicine_retention"
                    ],

                "number_retention":
                    data[
                        "number_retention"
                    ],

                "code_switch_retention":
                    data[
                        "code_switch_retention"
                    ],
            }
        )


# ============================================================
# SCRIPT + REVIEW-GATE OVERALL SUMMARY
# ============================================================

valid_scored_results = [
    item
    for item in results
    if not item.get(
        "error"
    )
]

script_scored = [
    item
    for item
    in valid_scored_results
    if item.get(
        "script_valid"
    )
    is not None
]

script_passed = sum(
    1
    for item
    in script_scored
    if item.get(
        "script_valid"
    )
)

low_confidence_total = sum(
    item.get(
        "low_confidence_segments",
        0,
    )
    or 0
    for item
    in valid_scored_results
)

low_confidence_flagged = sum(
    item.get(
        "low_confidence_flagged_for_review",
        0,
    )
    or 0
    for item
    in valid_scored_results
)

review_gate_failures = [
    item.get(
        "file"
    )
    for item
    in valid_scored_results
    if not item.get(
        "review_gate_pass",
        True,
    )
]

safety_metrics = {
    "script_correct_samples":
        script_passed,

    "script_scored_samples":
        len(
            script_scored
        ),

    "script_correctness_rate":
        (
            script_passed
            / len(
                script_scored
            )
            if script_scored
            else None
        ),

    "low_confidence_threshold":
        0.70,

    "low_confidence_segments":
        low_confidence_total,

    "low_confidence_segments_flagged_for_review":
        low_confidence_flagged,

    "low_confidence_review_recall":
        (
            low_confidence_flagged
            / low_confidence_total
            if low_confidence_total
            else None
        ),

    "review_gate_failures":
        review_gate_failures,
}



# ============================================================
# WRITE JSON
# ============================================================

JSON_OUT.write_text(
    json.dumps(
        {
            "system":
                "MediExplain+ final STT",

            "normalisation":
                (
                    "Unicode NFKC, punctuation removed, "
                    "Arabic-script digits normalised; "
                    "no transliteration or translation."
                ),

            "per_file":
                results,

            "per_language":
                summary,

            "overall":
                overall,

            "safety_metrics":
                safety_metrics,
        },
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
    "=" * 92
)

print(
    "FINAL LANGUAGE SUMMARY"
)

print(
    "=" * 92
)

print(
    f"{'Language':<22}"
    f"{'N':>5}"
    f"{'Mean WER':>12}"
    f"{'Median':>12}"
    f"{'Meds':>11}"
    f"{'Numbers':>11}"
    f"{'Code-switch':>14}"
)

print(
    "-" * 92
)


for group, data in summary.items():

    wer_mean = (
        data["wer"]["mean"]
        if data["wer"]
        else None
    )

    wer_median = (
        data["wer"]["median"]
        if data["wer"]
        else None
    )


    print(
        f"{data['label']:<22}"
        f"{data['samples']:>5}"
        f"{percent(wer_mean):>12}"
        f"{percent(wer_median):>12}"
        f"{percent(data['medicine_retention']):>11}"
        f"{percent(data['number_retention']):>11}"
        f"{percent(data['code_switch_retention']):>14}"
    )


print()
print(
    f"Overall samples: "
    f"{overall['samples']}"
)

print(
    f"Overall mean WER: "
    f"{percent(overall['wer']['mean'])}"
)

print()
print(
    "Results written to:"
)

print(
    f"  {DETAIL_OUT.relative_to(ROOT)}"
)

print(
    f"  {SUMMARY_OUT.relative_to(ROOT)}"
)

print(
    f"  {JSON_OUT.relative_to(ROOT)}"
)