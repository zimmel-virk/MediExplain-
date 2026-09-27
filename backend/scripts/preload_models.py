#!/usr/bin/env python3
"""Optional one-time download/warm-up for the local AI models.

Weights are large; normal startup also downloads them lazily on first use.
"""
from app.core.config import settings

# This optional setup script preloads the main local AI models used by
# MediExplain+ so their weights are already available before the application is
# demonstrated or evaluated. It warms up faster-whisper for speech recognition,
# NLLB-200 for translation, the configured NLI model when enabled, and the local
# MMS-TTS voices for supported languages. Diarisation is intentionally left lazy
# because its pyannote model may require separate Hugging Face access and licensing.

def main():
    print("Preloading faster-whisper:", settings.WHISPER_MODEL)
    from app.services import stt
    stt._get_model()

    print("Preloading translation:", settings.NLLB_MODEL)
    from app.services import translation
    translation._load()

    if settings.NLI_ENABLED:
        print("Preloading NLI:", settings.NLI_MODEL)
        from app.services import nli
        nli._load()

    print("Preloading local TTS weights...")
    from transformers import AutoTokenizer, VitsModel
    for code, meta in settings.SUPPORTED_LANGUAGES.items():
        suffix = meta.get("tts")
        if not suffix:
            continue
        # Shahmukhi shares the Punjabi MMS model with Gurmukhi.
        model_id = f"facebook/mms-tts-{suffix}"
        try:
            AutoTokenizer.from_pretrained(model_id, cache_dir=settings.MODEL_CACHE_DIR)
            VitsModel.from_pretrained(model_id, cache_dir=settings.MODEL_CACHE_DIR)
            print("  ✓", code, model_id)
        except Exception as exc:
            print("  !", code, model_id, "—", exc)

    print("Model preload complete.")
    print("Diarisation remains lazy because pyannote may require an accepted model licence + HF_TOKEN.")


if __name__ == "__main__":
    main()
