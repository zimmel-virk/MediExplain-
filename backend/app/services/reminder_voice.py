"""
MediExplain+ medication reminder voice.

This module is ONLY for medication reminders.
Consultation/summary audio is deliberately untouched.

Language rule:
    English patient  -> English reminder
    Urdu patient     -> Urdu reminder
    Punjabi patient  -> Punjabi reminder

Punjabi remains Shahmukhi in the UI.
Gurmukhi is used internally only as the speech-engine input.
"""


# This file generates spoken medication reminders separately from the main
# consultation-summary audio workflow. It routes English and Urdu reminder text
# directly to their matching gTTS voices, while Punjabi reminders remain visible
# to the patient in Shahmukhi but use a Gurmukhi Punjabi version internally for
# speech generation. The language checks prevent a reminder from being spoken in
# a substitute language when the correct patient-language input is unavailable.
# Generated reminder audio is cached so identical reminders can be reused without
# running the speech service again.

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.core.config import settings


def _clean(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip(),
    )


def _contains_gurmukhi(value):
    return any(
        "\u0A00" <= ch <= "\u0A7F"
        for ch in str(value or "")
    )


def _cache_path(
    text: str,
    lang: str,
) -> Path:

    settings.AUDIO_CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    digest = hashlib.sha256(
        (
            "reminder-gtts-v2"
            + "\n"
            + lang
            + "\n"
            + text
        ).encode("utf-8")
    ).hexdigest()[:20]

    return (
        settings.AUDIO_CACHE_DIR
        / f"reminder_{lang}_{digest}.mp3"
    )


def synthesise(
    text: str,
    lang: str,
    alternate: str | None = None,
):
    """
    Generate medication-reminder audio only.

    Signature intentionally matches tts.synthesise()
    so schedules.py can use it without changing the
    rest of the reminder workflow.
    """

    text = _clean(text)
    alternate = _clean(alternate)

    if not text:
        return None


    # --------------------------------------------------------
    # ENGLISH
    # --------------------------------------------------------

    if lang == "en":
        speech_text = text
        voice_lang = "en"


    # --------------------------------------------------------
    # URDU
    # --------------------------------------------------------

    elif lang == "ur":
        speech_text = text
        voice_lang = "ur"


    # --------------------------------------------------------
    # PUNJABI
    # --------------------------------------------------------
    #
    # Visible text stays Shahmukhi.
    # Internal alternate must be true Punjabi Gurmukhi.
    # --------------------------------------------------------

    elif lang == "pa_shah":

        if not alternate:
            print(
                "Reminder Punjabi voice unavailable: "
                "Punjabi speech rendering is missing."
            )
            return None

        if not _contains_gurmukhi(alternate):
            print(
                "Reminder Punjabi voice blocked: "
                "speech input is not Punjabi Gurmukhi."
            )
            return None

        speech_text = alternate
        voice_lang = "pa"


    else:
      
        return None


    out = _cache_path(
        speech_text,
        lang,
    )

    if (
        out.exists()
        and out.stat().st_size > 1000
    ):
        return out


    try:
        from gtts import gTTS

        gTTS(
            text=speech_text,
            lang=voice_lang,
            slow=False,
        ).save(
            str(out)
        )

        if (
            out.exists()
            and out.stat().st_size > 1000
        ):
            return out

    except Exception as exc:

        print(
            f"Reminder TTS failed for {lang}:",
            exc,
        )


    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass

    return None
