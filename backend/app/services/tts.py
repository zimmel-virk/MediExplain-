"""Local-first multilingual text-to-speech.

Primary backend: Meta MMS-TTS through transformers. gTTS is an explicit,
disabled-by-default fallback because it sends text to an external service.
"""
from __future__ import annotations
import hashlib, logging
from pathlib import Path
from app.core.config import settings

logger=logging.getLogger(__name__)
_models={}
_last_backend={}

# Generated speech is cached from the input text, language and backend so the
# same patient audio does not need to be synthesised again on later requests.

def _cache_path(text:str,lang:str,backend:str)->Path:
    digest=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return settings.AUDIO_CACHE_DIR/f"{lang}_{backend}_{digest}.wav"

# This converts the MediExplain+ language configuration into the corresponding
# Meta MMS-TTS model identifier when a local MMS voice is available.

def _mms_model_id(lang:str)->str|None:
    meta=settings.SUPPORTED_LANGUAGES.get(lang,{})
    suffix=meta.get("tts")
    return f"facebook/mms-tts-{suffix}" if suffix else None


# This is the local Meta MMS-TTS inference route. The required VITS model and
# tokenizer are loaded from the configured model cache, reused after the first
# request, and run in evaluation mode to generate a WAV file for the patient.

def _try_mms(text:str,lang:str)->Path|None:
    model_id=_mms_model_id(lang)
    if not model_id: return None
    out=_cache_path(text,lang,"mms")
    if out.exists(): return out
    try:
        import torch
        from scipy.io.wavfile import write as wavwrite
        from transformers import VitsModel, AutoTokenizer
        key=model_id
        # Keep each loaded language model in memory so repeated TTS requests do not
# reload the same tokenizer and neural speech model from disk.
        if key not in _models:
            tok=AutoTokenizer.from_pretrained(model_id,cache_dir=settings.MODEL_CACHE_DIR)
            model=VitsModel.from_pretrained(model_id,cache_dir=settings.MODEL_CACHE_DIR)
            model.eval()
            _models[key]=(tok,model)
        tok,model=_models[key]
        inputs=tok(text,return_tensors="pt")
        # TTS is inference-only, so gradients are disabled while the neural waveform
# is generated from the tokenised patient text.

        with torch.no_grad():
            waveform=model(**inputs).waveform[0].cpu().float().numpy()
        wavwrite(out,rate=int(model.config.sampling_rate),data=waveform)
        return out
    except Exception as exc:
        logger.warning("MMS TTS failed for %s: %s",lang,exc)
        return None

# gTTS is retained only as an explicitly enabled cloud fallback. It is skipped
# completely when cloud TTS fallback is disabled in the project configuration.

def _try_gtts(text:str,lang:str)->Path|None:
    if not settings.ALLOW_CLOUD_TTS_FALLBACK: return None
    meta=settings.SUPPORTED_LANGUAGES.get(lang,{})
    voice={"pa_shah":"pa","ps":"ur","sd":"ur"}.get(lang,lang)
    out=settings.AUDIO_CACHE_DIR/f"{lang}_gtts_{hashlib.sha256(text.encode()).hexdigest()[:16]}.mp3"
    if out.exists(): return out
    try:
        from gtts import gTTS
        gTTS(text=text,lang=voice).save(str(out))
        return out
    except Exception as exc:
        logger.warning("gTTS fallback failed: %s",exc)
        return None


# This preserves the earlier MediExplain+ TTS route for languages that are still
# allowed to use the existing same-language fallback. The newer wrapper below
# decides whether this legacy path is safe to call for the requested language.

def _legacy_synthesise(
    text:str,
    lang:str,
    alternate_text:str|None=None,
)->Path|None:
# PA_SHAH_LOCAL_URDU_ROUTE
# Punjabi Shahmukhi remains the visible patient text.
# Audio uses the proven local Urdu MMS route with the
# supplied Urdu/Shahmukhi speech rendering.
    if lang == "pa_shah":
        _pa_voice_text = (
            alternate_text
            or text
            or ""
        ).strip()

        if not _pa_voice_text:
            return None

        return synthesise(
            _pa_voice_text,
            "ur",
            None,
        )

    if not text or not text.strip(): return None

  # Where an alternate Punjabi rendering is available, the legacy path can pass
# the speech-engine form separately from the Shahmukhi text shown in the UI.

    spoken=alternate_text if lang=="pa_shah" and alternate_text else text
    mms_lang="pa" if lang=="pa_shah" else lang
    result=_try_mms(spoken,mms_lang)
    if result:
        _last_backend[lang]="mms_local"
        return result
    result=_try_gtts(spoken,lang)
    _last_backend[lang]="gtts_cloud_fallback" if result else "none"
    return result

# This reports which backend the older TTS route used so the consultation
# metadata can preserve how the audio was produced.

def _legacy_backend_used(lang:str)->str:
    if lang == "pa_shah":
        return backend_used("ur")

    return _last_backend.get(lang,"mms_local")



# ============================================================
# The current patient-facing TTS route is handled by neural_voice. This layer
# keeps backend tracking in one place and prevents unsupported language
# substitution if the preferred neural voice cannot generate valid audio.



from . import neural_voice as _neural_voice


_LAST_TTS_BACKEND = {}


# This is the main TTS entry point used by the consultation workflow. It first
# asks the current neural voice layer to generate audio in the patient's selected
# language and records the backend used. If that fails, only languages permitted
# to use the existing same-language fallback continue to the legacy MMS/gTTS
# route; Punjabi, Pashto and Sindhi are stopped instead of being spoken using a
# different language.

def synthesise(
    text,
    lang,
    alternate=None,
):
    """
    Generate speech only in the requested patient's language.

    Punjabi Shahmukhi:
      displayed as Shahmukhi
      spoken using true Punjabi internal Gurmukhi

    Cross-language substitution is forbidden.
    """

    try:
        neural = _neural_voice.synthesise(
            text,
            lang,
            alternate,
        )

        if neural:
            # Store a clear backend label so later evaluation and consultation metadata can
# show which speech system produced the patient audio.
            if lang == "pa_shah":
                filename = str(neural)

                _LAST_TTS_BACKEND[lang] = (
                    "gtts_punjabi"
                    if "gtts_pa" in filename
                    else "edge_neural_punjabi"
                )
            else:
                if lang == "ps":
                    _LAST_TTS_BACKEND[lang] = (
                        "edge_neural_pashto"
                    )
                elif lang == "sd":
                    _LAST_TTS_BACKEND[lang] = (
                        "indic_mio_sindhi"
                    )
                else:
                    _LAST_TTS_BACKEND[lang] = (
                        "edge_neural"
                    )

            return neural

    except Exception as exc:
        print(
            f"Neural TTS failed for {lang}:",
            exc,
        )

# Punjabi, Pashto and Sindhi must not fall back to a different-language voice.
# If their dedicated neural route fails, audio generation stops and the text
# remains available for review instead of producing misleading speech.
    if lang in {"pa_shah", "ps", "sd"}:
        _LAST_TTS_BACKEND[lang] = "none"
        return None

# Other supported languages may continue to the existing fallback path when
# that fallback still represents the same requested patient language.
    result = _legacy_synthesise(
        text,
        lang,
        alternate,
    )

    if result:
        try:
            _LAST_TTS_BACKEND[lang] = (
                _legacy_backend_used(lang)
            )
        except Exception:
            _LAST_TTS_BACKEND[lang] = (
                "legacy_same_language"
            )
    else:
        _LAST_TTS_BACKEND[lang] = "none"

    return result

# This exposes the backend recorded for the most recent synthesis in each
# language so the rest of the application can store or display TTS provenance.
def backend_used(lang):
    return _LAST_TTS_BACKEND.get(
        lang,
        "none",
    )
