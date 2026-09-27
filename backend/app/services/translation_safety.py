"""Deterministic safety checks for translated patient summaries."""

from __future__ import annotations

import hashlib
import re


# ============================================================
# SCRIPT RANGES
# ============================================================
# These Unicode ranges are used to confirm that translated patient text appears
# in the writing system expected for the selected language and to catch scripts
# that should not appear in the final patient-facing output.
ARABIC_SCRIPT_RANGE = re.compile(
    r"[\u0600-\u06FF]"
)

DEVANAGARI_RANGE = re.compile(
    r"[\u0900-\u097F]"
)

GURMUKHI_RANGE = re.compile(
    r"[\u0A00-\u0A7F]"
)


# ============================================================
# DIGIT NORMALISATION
# ============================================================

# Numbers may appear using Western, Arabic-Indic or Urdu-style digits. Converting
# them into one common form allows numeric information such as doses and durations
# to be compared reliably between the English source and translated summary.
DIGIT_TRANSLATION = str.maketrans(
    {
        # Arabic-Indic
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

        # Eastern Arabic / Urdu
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
    }
)

# This helper converts supported digit styles into Western digits before any
# numeric comparison is performed.

def normalise_digits(
    text: str | None,
) -> str:

    return (
        text
        or ""
    ).translate(
        DIGIT_TRANSLATION
    )

# This extracts numeric values from text after digit normalisation so values in
# the source and translated summaries can be compared directly.
def numbers(
    text: str,
) -> list[str]:

    normalised = normalise_digits(
        text
    )

    return re.findall(
        r"\b\d+(?:[.,]\d+)?\b",
        normalised,
    )


# ============================================================
# MEDICATION TOKENS
# ============================================================
# Medication names are collected from the structured consultation data using the
# available original, canonical, generic and brand-name fields. Duplicate names
# are removed so each medication only needs to be checked once.
def medication_tokens(
    structured: dict | None,
) -> list[str]:

    out = []

    for medication in (
        (
            structured
            or {}
        ).get(
            "medications"
        )
        or []
    ):

        for key in (
            "name",
            "canonical_name",
            "generic_name",
            "brand_name",
        ):

            value = (
                medication.get(
                    key
                )
                or ""
            ).strip()

            if (
                value
                and value.casefold()
                not in {
                    existing.casefold()
                    for existing
                    in out
                }
            ):

                out.append(
                    value
                )

    return out


# ============================================================
# SCRIPT SAFETY
# ============================================================

# This checks whether the translated summary uses the script expected for the
# selected patient language. Arabic-derived patient languages reject Devanagari
# and Gurmukhi output, while the internal Punjabi "pa" route expects Gurmukhi.
def script_valid(
    text: str,
    language: str,
) -> bool:

    if language == "en":
        return True

    if language in {
        "ur",
        "ar",
        "ps",
        "sd",
        "pa_shah",
    }:

        # These languages are expected to use Arabic-derived
        # script in MediExplain+.
        #
        # Hindi / Devanagari must never leak into patient output.
        return bool(
            ARABIC_SCRIPT_RANGE.search(
                text
                or ""
            )
        ) and not bool(
            DEVANAGARI_RANGE.search(
                text
                or ""
            )
        ) and not bool(
            GURMUKHI_RANGE.search(
                text
                or ""
            )
        )

    if language == "pa":

        return bool(
            GURMUKHI_RANGE.search(
                text
                or ""
            )
        )

    return True


# ============================================================
# SAFETY VERIFICATION
# ============================================================
# This is the main deterministic translation-safety check. It compares numbers
# between the source and translated text, checks whether known medication names
# are still present, validates the target script and keeps a hash of the original
# source so the verification result can be tied back to the exact text checked.
# Medication transliteration into another script is not treated as automatically
# verified when exact spelling cannot be confirmed, so those cases remain marked
# for review instead of being assumed safe.

def verify(
    source: str,
    translated: str,
    language: str,
    structured: dict | None = None,
) -> dict:

    source_numbers = numbers(
        source
    )

    translated_numbers = numbers(
        translated
    )

    numeric_preserved = (
        sorted(
            source_numbers
        )
        ==
        sorted(
            translated_numbers
        )
    )


    medicines = (
        medication_tokens(
            structured
        )
    )


    # --------------------------------------------------------
    # MEDICATION NAME CHECK
    # --------------------------------------------------------
   
    # Exact spelling provides a deterministic medication check. If a medicine
    # has been transliterated into another script, this check deliberately leaves
    # it for review rather than assuming the new spelling represents the same drug.
    exact_medications = [
        medication
        for medication
        in medicines
        if medication.casefold()
        in (
            translated
            or ""
        ).casefold()
    ]


    medication_preserved = (
        len(
            exact_medications
        )
        ==
        len(
            medicines
        )
        if medicines
        else True
    )


    return {
        "source_hash":
            hashlib.sha256(
                (
                    source
                    or ""
                ).encode()
            ).hexdigest(),

        "numeric_preserved":
            numeric_preserved,

        "medication_preserved":
            medication_preserved,

        "script_valid":
            script_valid(
                translated,
                language,
            ),

        "source_numbers":
            source_numbers,

        "translated_numbers":
            translated_numbers,

        "medications_checked":
            medicines,

        "medications_exactly_preserved":
            exact_medications,

        "medication_review_required":
            bool(
                medicines
                and not medication_preserved
            ),
    }