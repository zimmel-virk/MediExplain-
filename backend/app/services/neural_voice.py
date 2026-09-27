
"""
MediExplain+ same-language neural TTS.

STRICT RULE:
Patient audio must remain in the patient's selected language.

Punjabi:
  patient display = Shahmukhi
  speech input = Punjabi Gurmukhi internally
  Edge Punjabi first
  Punjabi gTTS fallback
  NEVER Urdu
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import re
from pathlib import Path

from app.core.config import settings

# These are the neural voices used for languages that can be spoken directly
# through Edge TTS. Each supported language is mapped to the voice selected for
# patient-facing audio generation.

EDGE_VOICES = {
    "en": "en-GB-SoniaNeural",
    "ur": "ur-PK-UzmaNeural",
    "ar": "ar-EG-SalmaNeural",
    "ps": "ps-AF-LatifaNeural",
}

# This helper cleans the text before it is passed into any speech engine by
# trimming it and collapsing repeated whitespace.

def _clean(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or "").strip(),
    )

# This check confirms that the internal Punjabi speech text is written in
# Gurmukhi before it is sent to the Punjabi speech engines.
def _contains_gurmukhi(text):
    return any(
        "\u0A00" <= ch <= "\u0A7F"
        for ch in str(text or "")
    )

# This function creates a stable cache filename from the language, speech engine
# and text. Identical speech requests can therefore reuse existing audio instead
# of running the TTS model again.

def _cache_path(
    text,
    lang,
    engine,
    extension,
):
    settings.AUDIO_CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    digest = hashlib.sha256(
        (
            lang
            + "\n"
            + engine
            + "\n"
            + text
        ).encode("utf-8")
    ).hexdigest()[:20]

    return (
        settings.AUDIO_CACHE_DIR
        / f"{lang}_{engine}_{digest}.{extension}"
    )

# This function generates neural speech using the selected Microsoft Edge voice.
# Existing cached audio is returned first; otherwise the text is synthesised and
# the newly generated MP3 is saved for later reuse.
def _edge(
    text,
    lang,
    voice,
):
    out = _cache_path(
        text,
        lang,
        "edge",
        "mp3",
    )

    if (
        out.exists()
        and out.stat().st_size > 1000
    ):
        return out

    try:
        import edge_tts

        communicator = edge_tts.Communicate(
            text,
            voice,
            rate="-3%",
            volume="+8%",
        )

        communicator.save_sync(
            str(out)
        )

        if (
            out.exists()
            and out.stat().st_size > 1000
        ):
            return out

    except Exception as exc:
        print(
            f"Edge TTS unavailable for {lang}:",
            exc,
        )

    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass

    return None

# This function provides the Punjabi fallback using gTTS. The patient can still
# see Punjabi in Shahmukhi, while the internal speech version must be Gurmukhi
# Punjabi so the correct language is spoken rather than substituting Urdu.
def _gtts_punjabi(text):
    """
    TRUE Punjabi fallback.

    text must be Punjabi written internally in Gurmukhi.
    This is never displayed to the patient.
    """

    if not _contains_gurmukhi(text):
        print(
            "Punjabi gTTS blocked: "
            "speech input is not Gurmukhi Punjabi."
        )
        return None

    out = _cache_path(
        text,
        "pa_shah",
        "gtts_pa",
        "mp3",
    )

    if (
        out.exists()
        and out.stat().st_size > 1000
    ):
        return out

    try:
        from gtts import gTTS

        gTTS(
            text=text,
            lang="pa",
            slow=False,
        ).save(str(out))

        if (
            out.exists()
            and out.stat().st_size > 1000
        ):
            return out

    except Exception as exc:
        print(
            "Punjabi gTTS failed:",
            exc,
        )

    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass

    return None



# ========================================================
# INDIC_MIO_SINDHI_PRODUCTION_V1
# ========================================================

# This function generates Sindhi patient audio through the isolated Indic-Mio
# neural TTS setup. The speech model runs in its own Python environment and uses
# MioCodec together with the stored Sindhi reference voice to produce the final
# WAV file. The generated audio is cached, and the function refuses to substitute
# another language if the Sindhi model or required files are unavailable.
def _sindhi_indic_mio(text):
    """
    Generate true Sindhi speech through the isolated
    Python 3.12 Indic-Mio + MioCodec environment.

    No cross-language audio substitution is allowed.
    """
    text = _clean(text)

    if not text:
        return None

    out = _cache_path(
        text,
        "sd",
        "indic_mio",
        "wav",
    )

    if (
        out.exists()
        and out.stat().st_size > 1000
    ):
        return out

    # Project root works on both local macOS and AWS.
    # neural_voice.py = project/backend/app/services/neural_voice.py
    root = Path(__file__).resolve().parents[3]

    python_executable = (
        root
        / "indic_mio_env"
        / "bin"
        / "python"
    )

    worker = (
        root
        / "indic_mio_sindhi_worker.py"
    )

    reference = (
        root
        / "backend"
        / "data"
        / "sindhi_voice_reference.wav"
    )

    if not python_executable.exists():
        print(
            "Sindhi TTS unavailable: "
            "isolated Python environment missing."
        )
        return None

    if not worker.exists():
        print(
            "Sindhi TTS unavailable: "
            "worker missing."
        )
        return None

    if not reference.exists():
        print(
            "Sindhi TTS unavailable: "
            "speaker reference missing."
        )
        return None

    try:
        # The Llama request has already completed by the
        # time TTS runs. Releasing Ollama's loaded model
        # gives the CPU-only Sindhi process sufficient RAM.
        try:
            subprocess.run(
                [
                    "ollama",
                    "stop",
                    "llama3.1:8b",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        except Exception:
            pass

        env = os.environ.copy()

        env[
            "HF_HOME"
        ] = str(
            root / "indic_mio_cache"
        )

        env[
            "TOKENIZERS_PARALLELISM"
        ] = "false"

        env[
            "OMP_NUM_THREADS"
        ] = "2"

        env[
            "MKL_NUM_THREADS"
        ] = "2"

        payload = json.dumps(
            {
                "text": text,
                "output": str(out),
                "reference": str(reference),
            },
            ensure_ascii=False,
        )

        completed = subprocess.run(
            [
                str(python_executable),
                str(worker),
            ],
            input=payload,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=900,
            check=False,
        )

        if completed.returncode != 0:
            print(
                "Sindhi Indic-Mio failed:",
                completed.stderr[-2000:],
            )
            try:
                if out.exists():
                    out.unlink()
            except Exception:
                pass
            return None

        if (
            out.exists()
            and out.stat().st_size > 1000
        ):
            return out

        print(
            "Sindhi Indic-Mio produced "
            "no valid audio."
        )

    except Exception as exc:
        print(
            "Sindhi Indic-Mio unavailable:",
            exc,
        )

    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass

    return None

# This is the main language-routing function for patient speech output. Punjabi
# uses its Gurmukhi speech rendering with Edge TTS first and Punjabi gTTS as the
# fallback, Sindhi is routed to Indic-Mio, and the remaining supported languages
# use their configured Edge neural voices. The routing keeps speech in the
# patient's selected language instead of falling back to a different language.


def synthesise(
    text,
    lang,
    alternate=None,
):
    text = _clean(text)
    alternate = _clean(alternate)

    if not text:
        return None

    # ========================================================
    # PUNJABI SHAHMUKHI
    # ========================================================

    if lang == "pa_shah":

        if not alternate:
            print(
                "Punjabi TTS blocked: "
                "Punjabi internal rendering is missing."
            )
            return None

        if not _contains_gurmukhi(alternate):
            print(
                "Punjabi TTS blocked: "
                "internal speech text is not Punjabi."
            )
            return None

        # First try the better Punjabi neural voice.
        audio = _edge(
            alternate,
            "pa_shah",
            "pa-IN-VaaniNeural",
        )

        if audio:
            return audio

        # Microsoft Punjabi is currently unreliable.
        # Fallback remains PUNJABI, not Urdu.
        return _gtts_punjabi(
            alternate
        )

    # ========================================================
    # SINDHI
    # ========================================================

    if lang == "sd":
        return _sindhi_indic_mio(
            text
        )

    # ========================================================
    # OTHER NEURAL LANGUAGES
    # ========================================================

    if lang in EDGE_VOICES:
        return _edge(
            text,
            lang,
            EDGE_VOICES[lang],
        )

    return None
