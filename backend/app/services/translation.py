"""Local NLLB-200 translation with deterministic
script and clinical-safety metadata.
"""

from __future__ import annotations

import hashlib
import logging
import re

from app.core.config import settings

from app.services.script_policy import (
    ScriptPolicyError,
    enforce_script,
)

from app.services.translation_safety import (
    verify as verify_translation,
)
# This file handles the main multilingual translation stage used by MediExplain+.
# NLLB-200 produces patient-language translations locally, while additional safety
# checks verify script, numbers and medication preservation before the translation
# is treated as suitable for delivery. For supported languages, a back-translation
# can also be compared with the English source using the NLI grounding model so
# semantic changes are surfaced for review instead of being silently accepted.

logger = logging.getLogger(__name__)

_tokenizer = None
_model = None
_device = None


# Internal model representations.
# These are NOT exposed as patient-language options.
_INTERNAL_NLLB_CODES = {
    "pa": "pan_Guru",
    "hi": "hin_Deva",
}

# This loads the configured NLLB-200 tokenizer and sequence-to-sequence model,
# selects the best available device and keeps the model in memory so later
# translations can reuse the same loaded instance.

def _load():
    global _tokenizer
    global _model
    global _device

    if _model is not None:
        return (
            _tokenizer,
            _model,
            _device,
        )

    import torch

    from transformers import (
        AutoModelForSeq2SeqLM,
        AutoTokenizer,
    )

    if torch.backends.mps.is_available():
        _device = "mps"
    elif torch.cuda.is_available():
        _device = "cuda"
    else:
        _device = "cpu"

    _tokenizer = (
        AutoTokenizer.from_pretrained(
            settings.NLLB_MODEL,
            cache_dir=
                settings.MODEL_CACHE_DIR,
        )
    )

    _model = (
        AutoModelForSeq2SeqLM
        .from_pretrained(
            settings.NLLB_MODEL,
            cache_dir=
                settings.MODEL_CACHE_DIR,
        )
        .to(_device)
    )

    _model.eval()

    return (
        _tokenizer,
        _model,
        _device,
    )

# MediExplain+ uses short language codes internally, while NLLB requires its own
# language identifiers. This helper converts between the two representations,
# including internal Punjabi and Hindi codes used by the translation workflow.

def _lang_code(
    short: str,
) -> str:
    if short in _INTERNAL_NLLB_CODES:
        return _INTERNAL_NLLB_CODES[
            short
        ]

    meta = (
        settings
        .SUPPORTED_LANGUAGES
        .get(short)
    )

    if not meta:
        raise ValueError(
            f"Unsupported language: {short}"
        )

    return meta["nllb"]

# Longer patient summaries are split into sentences before translation so each
# part stays within the model input limit while preserving normal sentence order.

def _split(
    text: str,
) -> list[str]:
    return [
        x
        for x in re.split(
            r"(?<=[.!?؟])\s+",
            (text or "").strip(),
        )
        if x
    ]

# This is the direct NLLB-200 inference stage. Each sentence is tokenised using
# the source-language code and generated with the requested target-language token,
# then the translated sentences are joined back into one patient summary.

def translate_nllb(
    text: str,
    source: str,
    target: str,
) -> str:
    if (
        source == target
        or not text.strip()
    ):
        return text

    tok, model, device = _load()

    tok.src_lang = _lang_code(
        source
    )

    target_id = (
        tok.convert_tokens_to_ids(
            _lang_code(target)
        )
    )

    parts = []

    for sentence in _split(
        text
    ):
        inputs = tok(
            sentence,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        ).to(device)

        out = model.generate(
            **inputs,
            forced_bos_token_id=
                target_id,
            max_length=512,
            num_beams=4,
        )

        translated = (
            tok.batch_decode(
                out,
                skip_special_tokens=True,
            )[0]
            .strip()
        )

        parts.append(
            translated
        )

    return " ".join(
        parts
    )

# This is the main translation route used by the application. Normal languages
# are translated directly with NLLB and then checked against the required script.
# Shahmukhi Punjabi is handled specially because NLLB produces Punjabi internally
# in Gurmukhi, which is mechanically converted into Shahmukhi before the final
# patient-facing script policy is enforced.

def translate(
    text: str,
    source: str = "en",
    target: str = "ur",
) -> str:
    if not text.strip():
        return text

    if source == target:
        return enforce_script(
            text,
            target,
        )

    if target == "pa_shah":
        from app.services.shahmukhi import (
            mechanical_transliterate,
        )

# NLLB produces Punjabi in Gurmukhi internally; this intermediate result is
# converted to Shahmukhi before it is validated and exposed as patient text.
        gurmukhi = translate_nllb(
            text,
            source,
            "pa",
        )

        shahmukhi = (
            mechanical_transliterate(
                gurmukhi
            )
        )

        return enforce_script(
            shahmukhi,
            "pa_shah",
        )

    translated = translate_nllb(
        text,
        source,
        target,
    )

    return enforce_script(
        translated,
        target,
    )


# This runs translation together with the safety checks needed for patient-facing
# delivery. It records a hash of the English source, blocks invalid scripts,
# verifies numbers and medication names, performs back-translation where supported
# and uses the NLI model to compare the back-translated meaning with the source.
# The final quality label reflects these checks so uncertain translations remain
# review-required instead of being treated as automatically verified.

def translate_with_metadata(
    text: str,
    source: str = "en",
    target: str = "ur",
    structured: dict | None = None,
) -> dict:

    source_hash = hashlib.sha256(
        (text or "").encode(
            "utf-8"
        )
    ).hexdigest()

    try:
        translated = translate(
            text,
            source,
            target,
        )

    except ScriptPolicyError as exc:
        logger.error(
            "Translation blocked by "
            "script policy: %s",
            exc,
        )

        return {
            "translated": "",
            "source": source,
            "target": target,
            "quality":
                "blocked_script",
            "dose_sentences": [],
            "back_translation": None,
            "semantic_status":
                "blocked",
            "semantic_score": None,
            "numeric_preserved":
                False,
            "medication_preserved":
                False,
            "script_valid":
                False,
            "script_error":
                str(exc),
            "source_hash":
                source_hash,
        }

    check = verify_translation(
        text,
        translated,
        target,
        structured,
    )

    # Script-policy result is authoritative.
    # Script validation is applied again to the completed translation metadata so
# the stored safety result reflects the same policy used during translation.
    try:
        enforce_script(
            translated,
            target,
        )
        check["script_valid"] = True

    except ScriptPolicyError as exc:
        check["script_valid"] = False
        check["script_error"] = (
            str(exc)
        )

    back = None
    semantic_status = "unavailable"
    semantic_score = None

    try:
        # NLLB does not directly accept Shahmukhi
        # as its Punjabi source representation.
        if target != "pa_shah":
            back = translate(
                translated,
                target,
                "en",
            )

            from app.services.nli import (
                check_pair,
            )

            sem = check_pair(
                text,
                back,
            )

            if sem.get(
                "available"
            ):
                semantic_score = (
                    sem.get(
                        "entailment",
                        0.0,
                    )
                )

                semantic_status = (
                    "pass"
                    if semantic_score
                    >= settings
                    .TRANSLATION_SEMANTIC_THRESHOLD
                    else "review"
                )

    except Exception as exc:
        logger.warning(
            "Translation semantic "
            "verification unavailable: %s",
            exc,
        )

# Numeric preservation and correct patient-language script are treated as
# critical requirements before the translation can receive a verified result.

    critical_ok = bool(
        check.get(
            "numeric_preserved"
        )
        and check.get(
            "script_valid"
        )
    )

    quality = (
        "verified"
        if (
            critical_ok
            and semantic_status
            == "pass"
        )
        else "review_required"
    )

# Sentences containing doses, units, frequencies or timing information are kept
# separately so medication-related translation content can be reviewed more easily.

    dose_sentences = [
        s
        for s in _split(text)
        if re.search(
            r"\d|mg|mcg|ml|tablet|"
            r"capsule|twice|three times|"
            r"daily|hour",
            s,
            re.I,
        )
    ]

    return {
        "translated":
            translated,
        "source":
            source,
        "target":
            target,
        "quality":
            quality,
        "dose_sentences":
            dose_sentences,
        "back_translation":
            back,
        "semantic_status":
            semantic_status,
        "semantic_score":
            semantic_score,
        "source_hash":
            source_hash,
        **check,
    }

# This asynchronous wrapper moves the synchronous translation work onto a worker
# thread so model inference does not block the application's async request flow.

async def translate_async(
    text: str,
    source: str = "en",
    target: str = "ur",
) -> str:
    import asyncio

    return await asyncio.to_thread(
        translate,
        text,
        source,
        target,
    )