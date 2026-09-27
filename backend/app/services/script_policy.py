"""Script safety rules for MediExplain+."""

from __future__ import annotations

import re
import unicodedata

# These patterns identify writing systems that should not appear in patient-facing
# output intended for Urdu, Shahmukhi Punjabi, Pashto, Sindhi or Arabic. They are
# used as a safeguard against translation output appearing in the wrong script.

DEVANAGARI_RE = re.compile(
    r"[\u0900-\u097F]"
)

GURMUKHI_RE = re.compile(
    r"[\u0A00-\u0A7F]"
)

ARABIC_SCRIPT_RE = re.compile(
    r"["
    r"\u0600-\u06FF"
    r"\u0750-\u077F"
    r"\u08A0-\u08FF"
    r"\uFB50-\uFDFF"
    r"\uFE70-\uFEFF"
    r"]"
)

ARABIC_SCRIPT_TARGETS = {
    "ur",
    "pa_shah",
    "ps",
    "sd",
    "ar",
}

# This exception is raised when translated patient text fails the required
# script policy and should not continue through the normal delivery workflow.

class ScriptPolicyError(ValueError):
    pass


# This helper checks whether Devanagari characters are present in the text.

def contains_devanagari(
    text: str | None,
) -> bool:
    return bool(
        DEVANAGARI_RE.search(
            text or ""
        )
    )

# This helper checks whether Gurmukhi characters are present in the text.
# Gurmukhi may be used internally for Punjabi speech generation, but it should
# not appear in the Shahmukhi text displayed to the patient.
def contains_gurmukhi(
    text: str | None,
) -> bool:
    return bool(
        GURMUKHI_RE.search(
            text or ""
        )
    )

# This helper detects whether text contains characters from the Arabic-script
# Unicode ranges used by the supported right-to-left patient languages.
def contains_arabic_script(
    text: str | None,
) -> bool:
    return bool(
        ARABIC_SCRIPT_RE.search(
            text or ""
        )
    )

# This function scans alphabetic characters for writing systems outside the
# expected Arabic or Latin scripts. Known Devanagari and Gurmukhi cases are
# handled separately so the final warning can identify those scripts clearly.
def _unexpected_scripts(
    text: str | None,
) -> list[str]:

    found = set()

    for char in text or "":

        if not char.isalpha():
            continue

        name = unicodedata.name(
            char,
            "",
        )

        # Expected scripts.
        if (
            "ARABIC" in name
            or "LATIN" in name
        ):
            continue

        # Reported explicitly elsewhere.
        if (
            "DEVANAGARI" in name
            or "GURMUKHI" in name
        ):
            continue

        if "BENGALI" in name:
            found.add("Bengali")

        elif "HEBREW" in name:
            found.add("Hebrew")

        elif "HANGUL" in name:
            found.add("Korean/Hangul")

        elif (
            "CJK" in name
            or "IDEOGRAPH" in name
        ):
            found.add("Chinese/CJK")

        elif (
            "HIRAGANA" in name
            or "KATAKANA" in name
        ):
            found.add("Japanese")

        elif "CYRILLIC" in name:
            found.add("Cyrillic")

        elif "GREEK" in name:
            found.add("Greek")

        elif "THAI" in name:
            found.add("Thai")

        else:
            found.add(
                name.split()[0]
                if name
                else "Unknown"
            )

    return sorted(found)



# This is the main script-safety check used for patient-language output.
# For Arabic-script target languages it reports Devanagari, Gurmukhi or other
# unexpected alphabets so incorrect translation-script output can be flagged
# before it is treated as safe patient-facing text.

def script_issues(
    text: str | None,
    target_language: str,
) -> list[str]:

    text = text or ""
    issues = []

    if (
        target_language
        not in ARABIC_SCRIPT_TARGETS
    ):
        return issues

    if contains_devanagari(text):
        issues.append(
            "Devanagari/Hindi script detected"
        )

    if contains_gurmukhi(text):
        issues.append(
            "Gurmukhi script detected"
        )

    unexpected = _unexpected_scripts(
        text
    )

    if unexpected:
        issues.append(
            "Unexpected alphabetic script(s): "
            + ", ".join(unexpected)
        )

    return issues

# This helper gives the rest of the translation pipeline a simple boolean result
# indicating whether the patient-facing text passed the script-safety checks.

def is_script_valid(
    text: str | None,
    target_language: str,
) -> bool:

    return not script_issues(
        text,
        target_language,
    )



# This function applies the script policy as a hard validation step. If an
# unexpected writing system is detected it raises ScriptPolicyError; otherwise
# the original text is returned unchanged.

def enforce_script(
    text: str,
    target_language: str,
) -> str:

    issues = script_issues(
        text,
        target_language,
    )

    if issues:
        raise ScriptPolicyError(
            f"{target_language}: "
            + "; ".join(issues)
        )

    return text
