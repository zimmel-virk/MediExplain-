"""Script safety rules for MediExplain+."""

from __future__ import annotations

import re
import unicodedata


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


class ScriptPolicyError(ValueError):
    pass


def contains_devanagari(
    text: str | None,
) -> bool:
    return bool(
        DEVANAGARI_RE.search(
            text or ""
        )
    )


def contains_gurmukhi(
    text: str | None,
) -> bool:
    return bool(
        GURMUKHI_RE.search(
            text or ""
        )
    )


def contains_arabic_script(
    text: str | None,
) -> bool:
    return bool(
        ARABIC_SCRIPT_RE.search(
            text or ""
        )
    )


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


def is_script_valid(
    text: str | None,
    target_language: str,
) -> bool:

    return not script_issues(
        text,
        target_language,
    )


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
