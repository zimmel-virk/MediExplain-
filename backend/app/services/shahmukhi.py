"""
Gurmukhi (ਪੰਜਾਬੀ) → Shahmukhi (پنجابی) script conversion.

Why this exists: NLLB-200 only supports Punjabi in Gurmukhi script. Pakistani
Punjabi readers expect Shahmukhi (Arabic-derived). We bridge by:

  1. Translating EN → Gurmukhi via NLLB (good quality)
  2. Converting Gurmukhi → Shahmukhi character-by-character (mechanical)
  3. Optionally polishing the result with the LLM, which knows both scripts
     and can fix the ambiguous cases the mechanical map can't

The mechanical map is not linguistically perfect — some Gurmukhi characters
have multiple valid Shahmukhi equivalents depending on context. We pick the
most common one. The LLM polish step (step 3) handles the rest.

This is documented in the UI as "Punjabi (Shahmukhi) — experimental".
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# This mapping provides the deterministic first stage of Punjabi script conversion.
# Each supported Gurmukhi character or sign is mapped to its most commonly used
# Shahmukhi equivalent, including vowels, consonants, nasalisation marks and
# punctuation. Because some Punjabi sounds depend on surrounding context, this
# character-level result is treated as an intermediate version rather than the
# final patient-facing translation.

_GUR_TO_SHAH = {
    # Vowels
    "ਅ": "ا", "ਆ": "آ", "ਇ": "ا", "ਈ": "ای", "ਉ": "ا",
    "ਊ": "او", "ਏ": "اے", "ਐ": "اے", "ਓ": "او", "ਔ": "او",
    # Vowel signs / diacritics
    "ਾ": "ا", "ਿ": "", "ੀ": "ی", "ੁ": "", "ੂ": "و",
    "ੇ": "ے", "ੈ": "ے", "ੋ": "و", "ੌ": "و",
    # Consonants
    "ਕ": "ک", "ਖ": "کھ", "ਗ": "گ", "ਘ": "گھ", "ਙ": "ن",
    "ਚ": "چ", "ਛ": "چھ", "ਜ": "ج", "ਝ": "جھ", "ਞ": "ن",
    "ਟ": "ٹ", "ਠ": "ٹھ", "ਡ": "ڈ", "ਢ": "ڈھ", "ਣ": "ن",
    "ਤ": "ت", "ਥ": "تھ", "ਦ": "د", "ਧ": "دھ", "ਨ": "ن",
    "ਪ": "پ", "ਫ": "پھ", "ਬ": "ب", "ਭ": "بھ", "ਮ": "م",
    "ਯ": "ی", "ਰ": "ر", "ਲ": "ل", "ਵ": "و", "ੜ": "ڑ",
    "ਸ": "س", "ਹ": "ہ",
    # Persian-Arabic loaned consonants (with nukta dot below)
    "ਖ਼": "خ", "ਗ਼": "غ", "ਜ਼": "ز", "ਫ਼": "ف", "ਸ਼": "ش", "ਲ਼": "ل", "ਨ਼": "ن",
    # Special signs
    "ੰ": "ں",    # tippi (nasalisation) → noon-ghunna
    "ਂ": "ں",    # bindi (nasalisation)
    "ੱ": "",     # addhak (gemination — drop for simplicity)
    "਼": "",     # nukta (drop — affects preceding consonant, already mapped)
    "੍": "",     # halant / virama (drops vowel — silent)
    "ਃ": "",     # visarga
    "ੴ": "",     # ek onkar — religious symbol, drop
    "ੲ": "ا",
    "ੳ": "ا",
    # Punctuation
    "।": "۔", "॥": "۔", "?": "؟",
}


# This function performs the deterministic Gurmukhi-to-Shahmukhi conversion
# without calling a language model. It substitutes characters using the mapping
# above and cleans the resulting spacing, providing a usable fallback even when
# the later LLM polishing step is unavailable.
def mechanical_transliterate(text: str) -> str:
    """
    Pure character-substitution Gurmukhi → Shahmukhi.
    Fast, deterministic, no internet/LLM needed. Quality: rough but readable.
    """
    if not text:
        return text
    out_chars = []
    for ch in text:
        out_chars.append(_GUR_TO_SHAH.get(ch, ch))
    out = "".join(out_chars)
    # Collapse runs of repeated empty positions (where diacritics were dropped)
    out = re.sub(r"\s+", " ", out).strip()
    return out

# This prompt gives the local LLM a tightly limited editing role after mechanical
# transliteration. The model receives both the original Gurmukhi Punjabi and the
# mechanically converted Shahmukhi version, then corrects contextual spelling and
# script ambiguities while being instructed to preserve Punjabi meaning, vocabulary
# and numbers rather than translating the content into Urdu or adding information.
_POLISH_SYSTEM = """You are an expert in Pakistani Punjabi written in Shahmukhi
(Arabic-derived script). You will receive Punjabi text in Gurmukhi script and a
mechanical character-by-character Shahmukhi version of it.

Produce the CORRECT Shahmukhi version. Rules:
- Keep the same meaning. Do NOT translate to Urdu — keep Punjabi vocabulary.
- Fix any spelling that doesn't match natural written Pakistani Punjabi.
- Use standard Shahmukhi conventions (joining forms, proper noon-ghunna ں, etc.)
- Numbers stay as Arabic numerals (1,2,3) — do not convert to Eastern Arabic.
- Output only the cleaned Shahmukhi text. No preamble. No explanation."""


# This is the main Shahmukhi conversion workflow. It always creates the
# deterministic mechanical version first, then optionally sends both the original
# Gurmukhi text and that intermediate result to the local Ollama LLM for linguistic
# polishing. A valid model response becomes the final Shahmukhi text, while an
# empty response or model failure falls back to the mechanical version so the
# conversion remains available without silently switching to another language.
async def to_shahmukhi(gurmukhi_text: str, use_llm: bool = True) -> str:
    """
    Convert Gurmukhi-script Punjabi to Shahmukhi.

    If `use_llm=True` (default) and the LLM call succeeds, we get a polished
    output. Otherwise we fall back to mechanical transliteration so the user
    never sees an error.
    """
    if not gurmukhi_text or not gurmukhi_text.strip():
        return gurmukhi_text

    mechanical = mechanical_transliterate(gurmukhi_text)

    if not use_llm:
        return mechanical

    try:
        from app.services.llm import _call_ollama

        user_prompt = (
            f"GURMUKHI:\n{gurmukhi_text}\n\n"
            f"MECHANICAL SHAHMUKHI (to polish):\n{mechanical}\n\n"
            "Return only the corrected Shahmukhi text."
        )
        polished = await _call_ollama(_POLISH_SYSTEM, user_prompt)
        polished = polished.strip()
        if polished and len(polished) > 5:
            return polished
        logger.warning("LLM Shahmukhi polish returned empty; using mechanical")
        return mechanical
    except Exception as e:
        logger.warning(f"Shahmukhi LLM polish failed ({e}); using mechanical")
        return mechanical
