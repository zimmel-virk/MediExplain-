from __future__ import annotations
from faster_whisper.audio import decode_audio
from faster_whisper.vad import (
    VadOptions,
    get_speech_timestamps,
)
"""faster-whisper STT with code-switching, script enforcement
and optional diarisation.
"""

# This file contains the main speech-to-text pipeline used by MediExplain+.
# faster-whisper transcribes consultation audio, while additional processing
# handles multilingual and code-switched speech, language detection, transcript
# confidence, script validation and optional speaker diarisation. For mixed-language
# consultations, the audio is divided into real speech regions using VAD, each
# region is acoustically classified and then decoded using the appropriate Whisper
# language route. Punjabi receives additional handling so patient-visible Punjabi
# remains Shahmukhi. Low-confidence, unexpected-script or uncertain segments are
# preserved and marked for doctor review rather than silently rewriting the
# original speech evidence.

import inspect
import re
import logging
import math

from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.diarization import (
    attach_speakers,
    diarize,
)
from app.services.script_policy import (
    contains_arabic_script,
    contains_devanagari,
    contains_gurmukhi,
    is_script_valid,
)


logger = logging.getLogger(__name__)

_model = None


# No Whisper transcript prompts.
#
# Script safety is performed after ASR. Prompt text was
# observed leaking into clinical transcripts, so the final
# STT pipeline intentionally performs unbiased decoding.
LANGUAGE_PROMPTS = {}

# This loads the configured faster-whisper model using the selected device and
# compute type. The model instance is kept in memory after the first load so the
# same Whisper model can be reused for later consultation transcriptions.

def _get_model():
    global _model

    if _model is None:
        from faster_whisper import WhisperModel

        logger.info(
            "Loading Whisper %s",
            settings.WHISPER_MODEL,
        )

        _model = WhisperModel(
            settings.WHISPER_MODEL,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
        )

    return _model

# Whisper's average log probability and no-speech probability are combined here
# into a simpler segment confidence value used later when deciding which parts of
# the consultation should be highlighted for doctor review.

def _confidence(
    avg_logprob,
    no_speech,
):
    if avg_logprob is None:
        return None

    p = max(
        0.0,
        min(
            1.0,
            math.exp(
                float(avg_logprob)
            ),
        ),
    )

    if no_speech is not None:
        p *= max(
            0.0,
            1.0 - float(no_speech),
        )

    return round(
        p,
        4,
    )


def _whisper_language(
    language: Optional[str],
) -> Optional[str]:
    if not language:
        return None

    if language == "pa_shah":
        return "pa"

    meta = settings.SUPPORTED_LANGUAGES.get(
        language
    )

    if meta:
        return meta.get(
            "whisper",
            language,
        )

    return language


def _canonical_language(
    requested: Optional[str],
    detected: Optional[str],
) -> Optional[str]:
    if requested:
        if requested == "pa":
            return "pa_shah"

        return requested

    if detected == "pa":
        return "pa_shah"

    # Hindi is not a supported product language.
    # An automatically detected Hindi-like consultation
    # is retried as Urdu later.
    if detected == "hi":
        return "ur"

    return detected


def _prompt_for(
    language: Optional[str],
) -> Optional[str]:
    if not language:
        return None

    canonical = (
        "pa_shah"
        if language == "pa"
        else language
    )

    return LANGUAGE_PROMPTS.get(
        canonical
    )

# This applies the patient-language script rules to Whisper output before it is
# displayed. Punjabi Gurmukhi output is converted to Shahmukhi, while Urdu,
# Punjabi, Pashto, Sindhi and Arabic output is checked for the expected
# Arabic-derived script. Unexpected script output is preserved but marked as
# unsafe for automatic use so the doctor can review the original ASR evidence.

def _normalise_script(
    text: str,
    language: Optional[str],
) -> tuple[str, bool, str | None]:
    text = (text or "").strip()

    if not text:
        return text, True, None

    if language == "pa":
        language = "pa_shah"

    # Punjabi Whisper/NLLB may naturally emit Gurmukhi.
    # Convert it to Shahmukhi before anything is displayed.
    if language == "pa_shah":
        if contains_gurmukhi(text):
            try:
                from app.services.shahmukhi import (
                    mechanical_transliterate,
                )

                text = mechanical_transliterate(
                    text
                )
            except Exception as exc:
                logger.warning(
                    "Punjabi Shahmukhi conversion failed: %s",
                    exc,
                )

        valid_script = (
            is_script_valid(
                text,
                "pa_shah",
            )
            and contains_arabic_script(
                text
            )
        )

        if valid_script:
            return text, True, None

        # Preserve the RAW STT hypothesis.
        #
        # The application flags this segment for clinician
        # review instead of destroying the original evidence.
        # This also keeps WER/CER evaluation valid.
        return (
            text,
            False,
            (
                "Punjabi output was not valid Shahmukhi "
                "or contained an unexpected script."
            ),
        )

    if language in {
        "ur",
        "ps",
        "sd",
        "ar",
    }:
        valid_script = (
            is_script_valid(
                text,
                language,
            )
            and contains_arabic_script(
                text
            )
        )

        if valid_script:
            return text, True, None

        return (
            text,
            False,
            (
                f"Invalid or unexpected script detected "
                f"for {language}; clinician review required."
            ),
        )

    return text, True, None


# This performs a Whisper transcription pass with the project's VAD and decoding
# settings. It records the detected language, transcript segments, timestamps,
# confidence information and script-safety results while keeping segment times
# inside the physical duration of the original recording.

def _run_pass(
    audio_path: str | Path,
    language: Optional[str],
    multilingual: bool = False,
) -> dict:
    model = _get_model()

    whisper_language = _whisper_language(
        language
    )

    prompt = _prompt_for(
        language
    )

    params = inspect.signature(
        model.transcribe
    ).parameters

    multilingual_supported = (
        "multilingual"
        in params
    )

    use_multilingual = bool(
        multilingual
        and multilingual_supported
    )

    kwargs = {
        "beam_size":
            settings.WHISPER_BEAM_SIZE,

        "vad_filter":
            True,

        "vad_parameters": {
            "min_silence_duration_ms":
                400,
        },

        "condition_on_previous_text":
            False,

        "word_timestamps":
            False,
    }

    if prompt:
        kwargs["initial_prompt"] = prompt


    # --------------------------------------------------------
    # Native faster-whisper multilingual decoding.
    #
    # Crucially, this is ONE transcription pass.
    # We no longer run a second forced-English transcription
    # over the complete Urdu/Punjabi/etc. recording.
    # --------------------------------------------------------

    if use_multilingual:

        kwargs["language"] = None
        kwargs["multilingual"] = True

        if (
            "language_detection_threshold"
            in params
        ):
            kwargs[
                "language_detection_threshold"
            ] = 0.55

        if (
            "language_detection_segments"
            in params
        ):
            kwargs[
                "language_detection_segments"
            ] = 1

    else:

        kwargs[
            "language"
        ] = whisper_language


    segments_iterator, info = (
        model.transcribe(
            str(
                audio_path
            ),
            **kwargs,
        )
    )

    detected = getattr(
        info,
        "language",
        None,
    )

    # Whisper timestamps must never extend outside the
    # physical recording. Some multilingual decodes can
    # occasionally return an end timestamp beyond the
    # reported/decoded audio duration.
    authoritative_duration = float(
        getattr(
            info,
            "duration",
            0.0,
        )
        or 0.0
    )

    canonical_language = (
        _canonical_language(
            language,
            detected,
        )
    )

    output = []

    for segment in segments_iterator:

        avg = getattr(
            segment,
            "avg_logprob",
            None,
        )

        no_speech = getattr(
            segment,
            "no_speech_prob",
            None,
        )

        original_text = (
            segment.text
            or ""
        ).strip()

        if not original_text:
            continue

        raw_start = float(
            segment.start
        )

        raw_end = float(
            segment.end
        )

        timestamp_clamped = False

        segment_start = max(
            0.0,
            raw_start,
        )

        segment_end = raw_end

        if authoritative_duration > 0:
            segment_start = min(
                segment_start,
                authoritative_duration,
            )

            segment_end = min(
                segment_end,
                authoritative_duration,
            )

        segment_end = max(
            segment_start,
            segment_end,
        )

        if (
            abs(
                segment_start
                - raw_start
            )
            > 0.01
            or abs(
                segment_end
                - raw_end
            )
            > 0.01
        ):
            timestamp_clamped = True

        # Ignore zero-length regions after enforcing the
        # physical recording boundary.
        if (
            segment_end
            - segment_start
        ) < 0.02:
            continue


        # With multilingual decoding the decoder itself changes
        # language by speech chunk. We infer the display language
        # from the produced script rather than trusting a forced
        # whole-file English pass.
        if use_multilingual:

            segment_language = (
                _infer_segment_language(
                    original_text,
                    canonical_language,
                )
            )

        else:

            segment_language = (
                canonical_language
            )


        (
            display_text,
            script_valid,
            script_issue,
        ) = _normalise_script(
            original_text,
            segment_language,
        )


        output.append(
            {
                "start":
                    segment_start,

                "end":
                    segment_end,

                "raw_start":
                    raw_start,

                "raw_end":
                    raw_end,

                "timestamp_clamped":
                    timestamp_clamped,

                "needs_review":
                    timestamp_clamped,

                "text":
                    display_text,

                "avg_logprob":
                    avg,

                "no_speech_prob":
                    no_speech,

                "confidence":
                    _confidence(
                        avg,
                        no_speech,
                    ),

                "language":
                    segment_language,

                "script_valid":
                    script_valid,

                "script_issue":
                    script_issue,
            }
        )


    return {
        "language":
            canonical_language,

        "detected_whisper_language":
            detected,

        "language_probability":
            getattr(
                info,
                "language_probability",
                None,
            ),

        "duration":
            float(
                info.duration
            ),

        "segments":
            output,

        "multilingual_supported":
            multilingual_supported,

        "multilingual_used":
            use_multilingual,
    }



def _overlap(
    a,
    b,
):
    return max(
        0.0,
        min(
            a["end"],
            b["end"],
        )
        - max(
            a["start"],
            b["start"],
        ),
    )

ARABIC_FAMILY = {
    "ur",
    "pa_shah",
    "ps",
    "sd",
    "ar",
}


def _latin_words(
    text: str,
) -> list[str]:
    return re.findall(
        r"[A-Za-z][A-Za-z'-]*",
        text or "",
    )


def _has_arabic_script(
    text: str,
) -> bool:
    return bool(
        re.search(
            r"[\u0600-\u06FF]",
            text or "",
        )
    )


def _has_gurmukhi(
    text: str,
) -> bool:
    return bool(
        re.search(
            r"[\u0A00-\u0A7F]",
            text or "",
        )
    )


def _has_devanagari(
    text: str,
) -> bool:
    return bool(
        re.search(
            r"[\u0900-\u097F]",
            text or "",
        )
    )

# This identifies the display language of a Whisper segment from its script and
# the consultation's dominant language. It helps recognise genuine English
# phrases inside multilingual speech while keeping Punjabi and other
# Arabic-script languages on their intended patient-facing language route.

def _infer_segment_language(
    text: str,
    primary_language: str | None,
) -> str:
    """
    Infer a display language from the script produced by the
    native multilingual Whisper decoding.

    This does NOT run another transcription.
    """

    primary = (
        primary_language
        or "en"
    )


    # Punjabi Gurmukhi may be produced internally by Whisper;
    # MediExplain+ converts it to Shahmukhi for display.
    if _has_gurmukhi(
        text
    ):
        return "pa_shah"


    # Arabic-derived scripts include Urdu, Shahmukhi,
    # Pashto, Sindhi and Arabic.
    if _has_arabic_script(
        text
    ):

        if primary in ARABIC_FAMILY:
            return primary

        # If the dominant language was English but a chunk is
        # clearly Arabic-script speech, Urdu is only a display
        # fallback. The downstream doctor review remains active.
        return "ur"


    # Devanagari must never silently become valid Urdu.
    # Keep the intended primary language so script validation
    # can reject it.
    if _has_devanagari(
        text
    ):

        if primary in ARABIC_FAMILY:
            return primary

        return primary


    # A genuinely Latin-script speech chunk is treated as
    # English only when it contains a real phrase rather than
    # a single medicine/abbreviation token.
    if len(
        _latin_words(
            text
        )
    ) >= 2:
        return "en"


    return primary


def _segment_overlap_ratio(
    a: dict,
    b: dict,
) -> float:

    overlap = _overlap(
        a,
        b,
    )

    shorter = min(
        max(
            a["end"]
            - a["start"],
            0.001,
        ),
        max(
            b["end"]
            - b["start"],
            0.001,
        ),
    )

    return (
        overlap
        / shorter
    )


def _dedupe_key(
    text: str,
) -> str:

    return re.sub(
        r"\W+",
        " ",
        (
            text
            or ""
        ).casefold(),
        flags=re.UNICODE,
    ).strip()

# Whisper or region-based decoding can occasionally produce the same text over
# substantially overlapping timestamps. This removes those duplicate ASR
# segments and keeps the higher-confidence version so repeated transcript text
# is not passed into the later clinical pipeline.

def _dedupe_segments(
    segments: list[dict],
) -> list[dict]:
    """
    Remove duplicate ASR segments occupying essentially the
    same time region.

    Consultation 31 exposed identical 0-6.56 and 6.56-12.56
    segments being stored twice.
    """

    ordered = sorted(
        segments,
        key=lambda s: (
            s["start"],
            s["end"],
        ),
    )

    result = []

    for candidate in ordered:

        candidate_key = (
            _dedupe_key(
                candidate.get(
                    "text",
                    "",
                )
            )
        )

        duplicate_index = None

        for index, existing in enumerate(
            result
        ):

            if (
                candidate_key
                and candidate_key
                ==
                _dedupe_key(
                    existing.get(
                        "text",
                        "",
                    )
                )
                and _segment_overlap_ratio(
                    candidate,
                    existing,
                )
                >= 0.80
            ):
                duplicate_index = (
                    index
                )
                break


        if duplicate_index is None:

            result.append(
                candidate
            )

            continue


        existing = result[
            duplicate_index
        ]

        candidate_confidence = (
            candidate.get(
                "confidence"
            )
            or 0.0
        )

        existing_confidence = (
            existing.get(
                "confidence"
            )
            or 0.0
        )

        if (
            candidate_confidence
            >
            existing_confidence
        ):
            result[
                duplicate_index
            ] = candidate


    result.sort(
        key=lambda s: (
            s["start"],
            s["end"],
        )
    )

    return result


def _detected_languages(
    segments: list[dict],
    primary_language: str | None,
) -> set[str]:

    languages = set()

    if primary_language:
        languages.add(
            primary_language
        )


    for segment in segments:

        language = (
            segment.get(
                "language"
            )
        )

        if language:
            languages.add(
                language
            )


        # Mixed script inside one segment can also be genuine
        # code-switching, e.g. Urdu sentence + English phrase.
        text = (
            segment.get(
                "text"
            )
            or ""
        )

        if (
            language != "en"
            and len(
                _latin_words(
                    text
                )
            )
            >= 2
        ):
            languages.add(
                "en"
            )


    return languages



# === PHASE17 ACOUSTIC CODE-SWITCH START ===

SUPPORTED_DISPLAY_LANGUAGES = {
    "en",
    "ur",
    "pa_shah",
    "ps",
    "sd",
    "ar",
}


def _language_probability_map(
    probabilities,
) -> dict[str, float]:

    return {
        str(language):
            float(probability)

        for language, probability
        in (
            probabilities
            or []
        )
    }

# This converts Whisper's acoustic language probabilities into one of the
# languages supported by MediExplain+. It uses the dominant consultation
# language as context for closely related speech such as Urdu, Hindi and Punjabi,
# while requiring stronger acoustic evidence before a region is treated as
# English during code-switching.

def _resolve_acoustic_language(
    detected: str | None,
    probability: float | None,
    probabilities,
    primary_language: str | None,
    explicit_secondary:
        str | None = None,
) -> str:
    """
    Convert Whisper's acoustic language decision into one of
    MediExplain+'s supported display languages.

    Hindi/Urdu are extremely close acoustically. If the
    consultation's dominant language is Urdu and a region is
    classified as Hindi, preserve the consultation language
    and transcribe that region as Urdu.

    English is accepted only with strong acoustic evidence.
    """

    primary = (
        primary_language
        or "en"
    )

    probs = (
        _language_probability_map(
            probabilities
        )
    )

    english_probability = (
        probs.get(
            "en",
            0.0,
        )
    )


    # Strong English evidence.
    if english_probability >= 0.80:
        return "en"


    # --------------------------------------------------------
    # URDU
    # --------------------------------------------------------

    if primary == "ur":

        if detected in {
            "ur",
            "hi",
        }:
            return "ur"

        # Weak non-English uncertainty should not switch away
        # from the dominant Urdu consultation.
        if english_probability < 0.55:
            return "ur"


    # --------------------------------------------------------
    # PUNJABI SHAHMUKHI
    # --------------------------------------------------------

    if primary == "pa_shah":

        if detected in {
            "pa",
            "ur",
            "hi",
        }:
            return "pa_shah"

        if english_probability < 0.55:
            return "pa_shah"


    # --------------------------------------------------------
    # PASHTO / SINDHI / ARABIC
    # --------------------------------------------------------

    if primary in {
        "ps",
        "sd",
        "ar",
    }:

        if (
            detected
            == primary
        ):
            return primary

        if english_probability < 0.55:
            return primary


    # Explicit two-language evaluation mode.
    if (
        explicit_secondary
        and detected
        == explicit_secondary
    ):
        return explicit_secondary


    # Canonicalise Whisper's Punjabi language code.
    if detected == "pa":
        return "pa_shah"


    if (
        detected
        in SUPPORTED_DISPLAY_LANGUAGES
    ):
        return detected


    return primary


def _detect_region_language(
    model,
    audio,
    sample_rate: int,
    start: float,
    end: float,
    primary_language:
        str | None,
    secondary_language:
        str | None = None,
) -> dict:

    padding = 0.12

    clip_start = max(
        0,
        int(
            (
                start
                - padding
            )
            * sample_rate
        ),
    )

    clip_end = min(
        len(audio),
        int(
            (
                end
                + padding
            )
            * sample_rate
        ),
    )

    clip = audio[
        clip_start:clip_end
    ]


    try:

        (
            detected,
            probability,
            probabilities,
        ) = model.detect_language(
            audio=clip,
            vad_filter=False,
            language_detection_segments=1,
            language_detection_threshold=0.0,
        )


        resolved = (
            _resolve_acoustic_language(
                detected,
                probability,
                probabilities,
                primary_language,
                secondary_language,
            )
        )


        return {
            "language":
                resolved,

            "acoustic_language":
                detected,

            "language_confidence":
                float(
                    probability
                    or 0.0
                ),

            "language_candidates":
                [
                    [
                        str(lang),
                        round(
                            float(prob),
                            6,
                        ),
                    ]

                    for lang, prob
                    in (
                        probabilities[:5]
                        if probabilities
                        else []
                    )
                ],
        }


    except Exception as exc:

        logger.warning(
            "Segment language detection failed "
            "%.2f-%.2f: %s",
            start,
            end,
            exc,
        )

        return {
            "language":
                primary_language
                or "en",

            "acoustic_language":
                None,

            "language_confidence":
                0.0,

            "language_candidates":
                [],
        }


def _group_language_regions(
    regions: list[dict],
) -> list[dict]:
    """
    Merge adjacent speech regions when the acoustic detector
    says they are the same language.

    Consultation 31 becomes approximately:
      Urdu    0.00-2.66
      English 3.06-12.10
      Urdu   12.50-16.06
    """

    if not regions:
        return []


    regions = sorted(
        regions,
        key=lambda item:
            item["start"],
    )


    grouped = [
        dict(
            regions[0]
        )
    ]


    for region in regions[1:]:

        previous = (
            grouped[-1]
        )

        gap = (
            region["start"]
            - previous["end"]
        )


        if (
            region["language"]
            == previous["language"]
            and gap <= 0.55
        ):

            previous[
                "end"
            ] = max(
                previous["end"],
                region["end"],
            )

            previous.setdefault(
                "source_regions",
                [],
            )

            previous[
                "source_regions"
            ].append(
                region
            )


            previous[
                "language_confidence"
            ] = max(
                previous.get(
                    "language_confidence",
                    0.0,
                ),
                region.get(
                    "language_confidence",
                    0.0,
                ),
            )

        else:

            grouped.append(
                dict(
                    region
                )
            )


    return grouped


# Once an audio region has been classified by language, this function runs
# Whisper on that specific part of the recording using the appropriate language
# decoder. Pakistani Punjabi receives additional candidate decoding because the
# Punjabi and Urdu Whisper routes can produce different scripts; candidate
# outputs are compared using confidence and script validity, while the final
# patient-facing language remains Shahmukhi Punjabi.

def _transcribe_language_region(
    model,
    audio,
    sample_rate: int,
    region: dict,
) -> dict:
    """
    Force-decode one acoustically classified language region.

    Pakistani Punjabi/Shahmukhi gets TWO candidate decodes:

        1. Whisper Punjabi token: pa
        2. Whisper Urdu token: ur

    Punjabi audio is often represented inconsistently by
    multilingual Whisper. The Urdu decoder is therefore used
    only as a Shahmukhi/Perso-Arabic ASR fallback.

    The candidate with the strongest confidence AND valid
    Shahmukhi script is selected.

    Final display language always remains pa_shah.
    """

    language = region["language"]

    audio_duration = (
        len(audio)
        / sample_rate
    )

    start = max(
        0.0,
        min(
            float(region["start"]),
            audio_duration,
        ),
    )

    end = max(
        start,
        min(
            float(region["end"]),
            audio_duration,
        ),
    )

    # Small overlap helps preserve words directly beside
    # a Punjabi/English switch without allowing one decoder
    # to consume a large neighbouring-language region.
    padding = 0.25

    clip_start_seconds = max(
        0.0,
        start - padding,
    )

    clip_end_seconds = min(
        audio_duration,
        end + padding,
    )

    clip_start = int(
        clip_start_seconds
        * sample_rate
    )

    clip_end = int(
        clip_end_seconds
        * sample_rate
    )

    clip = audio[
        clip_start:clip_end
    ]


    def decode_candidate(
        whisper_language: str,
        clip_override=None,
    ) -> dict | None:

        try:

            decode_clip = (
                clip
                if clip_override is None
                else clip_override
            )

            iterator, _ = model.transcribe(
                decode_clip,
                language=whisper_language,
                beam_size=
                    settings.WHISPER_BEAM_SIZE,
                vad_filter=False,
                condition_on_previous_text=False,
                word_timestamps=False,
            )

            produced = list(
                iterator
            )

            raw_text = " ".join(
                (
                    segment.text
                    or ""
                ).strip()

                for segment
                in produced

                if (
                    segment.text
                    or ""
                ).strip()
            ).strip()

            if not raw_text:
                return None


            logprobs = [
                float(
                    segment.avg_logprob
                )

                for segment
                in produced

                if getattr(
                    segment,
                    "avg_logprob",
                    None,
                )
                is not None
            ]

            no_speech_values = [
                float(
                    segment.no_speech_prob
                )

                for segment
                in produced

                if getattr(
                    segment,
                    "no_speech_prob",
                    None,
                )
                is not None
            ]


            avg_logprob = (
                sum(logprobs)
                / len(logprobs)

                if logprobs
                else None
            )

            no_speech_prob = (
                max(
                    no_speech_values
                )

                if no_speech_values
                else None
            )

            confidence = _confidence(
                avg_logprob,
                no_speech_prob,
            )


            # IMPORTANT:
            # Even when Urdu decoder is used as a fallback,
            # validate/output according to Punjabi Shahmukhi.
            display_language = (
                "pa_shah"
                if language == "pa_shah"
                else language
            )

            (
                display_text,
                script_valid,
                script_issue,
            ) = _normalise_script(
                raw_text,
                display_language,
            )


            score = float(
                confidence
                or 0.0
            )


            # Strongly prefer valid display script.
            if script_valid:
                score += 0.40
            else:
                score -= 1.00


            # For Pakistani Punjabi, Arabic-derived output is
            # what we actually need to display.
            if language == "pa_shah":

                if contains_arabic_script(
                    display_text
                ):
                    score += 0.30

                if contains_devanagari(
                    display_text
                ):
                    score -= 2.00

                if contains_gurmukhi(
                    display_text
                ):
                    # This should normally already have been
                    # converted by _normalise_script().
                    score -= 1.00


            return {
                "text":
                    display_text,

                "raw_text":
                    raw_text,

                "avg_logprob":
                    avg_logprob,

                "no_speech_prob":
                    no_speech_prob,

                "confidence":
                    confidence,

                "script_valid":
                    script_valid,

                "script_issue":
                    script_issue,

                "decoder":
                    whisper_language,

                "score":
                    score,
            }

        except Exception as exc:

            logger.warning(
                "Region candidate decode failed "
                "%.2f-%.2f (%s via %s): %s",
                start,
                end,
                language,
                whisper_language,
                exc,
            )

            return None


    # --------------------------------------------------------
    # DECODER CANDIDATES
    # --------------------------------------------------------
    #
    # Pakistani Punjabi/Shahmukhi:
    # The Urdu decoder has repeatedly produced the usable
    # Perso-Arabic/Shahmukhi hypothesis on our real samples.
    #
    # Therefore decode with Urdu FIRST.
    #
    # Only spend time running Whisper's Punjabi decoder when
    # the Urdu result is missing, invalid, non-Arabic, or
    # extremely low confidence.
    # --------------------------------------------------------

    candidates = []

    if language == "pa_shah":

        ur_candidate = decode_candidate(
            "ur"
        )

        if ur_candidate:
            candidates.append(
                ur_candidate
            )


        ur_usable = bool(
            ur_candidate
            and ur_candidate.get(
                "script_valid"
            )
            and contains_arabic_script(
                ur_candidate.get(
                    "text"
                )
                or ""
            )
            and (
                ur_candidate.get(
                    "confidence"
                )
                or 0.0
            )
            >= 0.20
        )


        if not ur_usable:

            pa_candidate = (
                decode_candidate(
                    "pa"
                )
            )

            if pa_candidate:
                candidates.append(
                    pa_candidate
                )

    else:

        decoder_language = (
            _whisper_language(
                language
            )
        )

        if decoder_language:

            candidate = (
                decode_candidate(
                    decoder_language
                )
            )

            if candidate:
                candidates.append(
                    candidate
                )


    # --------------------------------------------------------
    # EMPTY ENGLISH REGION RETRY
    # --------------------------------------------------------
    #
    # Very short English terms directly beside Punjabi can
    # occasionally return no text. Retry ONCE with slightly
    # more physical context. The final region timestamps stay
    # unchanged.
    # --------------------------------------------------------

    if (
        not candidates
        and language == "en"
        and (
            end
            - start
        ) >= 3.0
    ):

        retry_padding = 0.55

        retry_start = max(
            0.0,
            start - retry_padding,
        )

        retry_end = min(
            audio_duration,
            end + retry_padding,
        )

        retry_clip = audio[
            int(retry_start * sample_rate):
            int(retry_end * sample_rate)
        ]

        retry_candidate = (
            decode_candidate(
                "en",
                clip_override=retry_clip,
            )
        )

        if retry_candidate:

            retry_candidate[
                "retry_expanded_context"
            ] = True

            candidates.append(
                retry_candidate
            )


    # --------------------------------------------------------
    # NOTHING DECODED
    # --------------------------------------------------------

    if not candidates:

        fallback = (
            region.get(
                "fallback_text"
            )
            or ""
        )

        (
            fallback,
            valid_script,
            script_issue,
        ) = _normalise_script(
            fallback,
            language,
        )

        return {
            "start":
                start,

            "end":
                end,

            "text":
                fallback,

            "avg_logprob":
                region.get(
                    "avg_logprob"
                ),

            "no_speech_prob":
                region.get(
                    "no_speech_prob"
                ),

            "confidence":
                region.get(
                    "confidence",
                    0.0,
                ),

            "language":
                language,

            "language_confidence":
                region.get(
                    "language_confidence"
                ),

            "acoustic_language":
                region.get(
                    "acoustic_language"
                ),

            "language_candidates":
                region.get(
                    "language_candidates",
                    [],
                ),

            "script_valid":
                valid_script,

            "script_issue":
                script_issue,

            "needs_review":
                True,

            "decoder_used":
                None,

            "decoder_candidates":
                [],
        }


    # --------------------------------------------------------
    # PICK BEST CANDIDATE
    # --------------------------------------------------------

    best = max(
        candidates,
        key=lambda candidate:
            candidate["score"],
    )


    needs_review = bool(
        region.get(
            "needs_review",
            False,
        )
        or not best[
            "script_valid"
        ]
        or (
            best[
                "confidence"
            ]
            is not None
            and best[
                "confidence"
            ]
            < 0.70
        )
    )


    return {
        "start":
            start,

        "end":
            end,

        "text":
            best["text"],

        "avg_logprob":
            best["avg_logprob"],

        "no_speech_prob":
            best[
                "no_speech_prob"
            ],

        "confidence":
            best["confidence"],

        "language":
            language,

        "language_confidence":
            region.get(
                "language_confidence"
            ),

        "acoustic_language":
            region.get(
                "acoustic_language"
            ),

        "language_candidates":
            region.get(
                "language_candidates",
                [],
            ),

        "script_valid":
            best[
                "script_valid"
            ],

        "script_issue":
            best[
                "script_issue"
            ],

        "needs_review":
            needs_review,

        "timestamp_clamped":
            bool(
                region.get(
                    "timestamp_clamped",
                    False,
                )
            ),

        # Useful evidence while we validate the final system.
        "decoder_used":
            best["decoder"],

        "decoder_candidates":
            [
                {
                    "decoder":
                        candidate[
                            "decoder"
                        ],

                    "confidence":
                        candidate[
                            "confidence"
                        ],

                    "script_valid":
                        candidate[
                            "script_valid"
                        ],

                    "score":
                        round(
                            candidate[
                                "score"
                            ],
                            4,
                        ),

                    "text":
                        candidate[
                            "text"
                        ],
                }

                for candidate
                in candidates
            ],
    }

# This handles genuine code-switched consultations using a detect-first,
# decode-second approach. Silero VAD first finds physical speech regions, short
# audio windows are checked for language acoustically, neighbouring windows of
# the same language are merged, and Whisper then transcribes each resulting
# region with the selected language decoder. This keeps language switching tied
# to the actual audio instead of relying on a second whole-recording transcript.

def _acoustic_code_switch_transcription(
    audio_path: str | Path,
    base_result: dict,
    primary_language:
        str | None,
    secondary_language:
        str | None = None,
) -> list[dict]:
    """
    Stable detect-first / decode-second code-switch pipeline.

    IMPORTANT:
    We do NOT use multilingual Whisper transcript text to
    decide the final transcript.

    Instead:

      1. Decode the real physical audio.
      2. Use Silero VAD to obtain real speech boundaries.
      3. Probe short physical windows acoustically.
      4. Decide whether each window is English or the
         dominant non-English consultation language.
      5. Merge neighbouring windows of the same language.
      6. Force-decode each merged region using the language
         token that already works well for monolingual STT.

    This avoids asking Whisper to both recognise speech and
    switch language inside one long decoder segment.
    """

    model = _get_model()

    sample_rate = (
        model
        .feature_extractor
        .sampling_rate
    )

    audio = decode_audio(
        str(audio_path),
        sampling_rate=sample_rate,
    )

    audio_duration = (
        len(audio)
        / sample_rate
    )

    if audio_duration <= 0:
        return []


    # --------------------------------------------------------
    # PHYSICAL SPEECH REGIONS
    # --------------------------------------------------------

 # These VAD settings define the real speech boundaries used by the acoustic
# code-switching pipeline while keeping short spoken terms around language
# switches from being removed as silence.

    vad_options = VadOptions(
        onset=0.45,
        offset=0.30,
        min_speech_duration_ms=120,
        min_silence_duration_ms=280,
        speech_pad_ms=100,
        max_speech_duration_s=30.0,
    )

    speech_chunks = (
        get_speech_timestamps(
            audio,
            vad_options=vad_options,
            sampling_rate=sample_rate,
        )
    )

    if not speech_chunks:
        speech_chunks = [
            {
                "start": 0,
                "end": len(audio),
            }
        ]


    # --------------------------------------------------------
    # DOMINANT NON-ENGLISH LANGUAGE
    # --------------------------------------------------------
    #
    # The whole-consultation detection remains useful as a
    # PRIOR, but its transcript is NOT used.
    # --------------------------------------------------------

    preferred_primary = (
        primary_language
        if primary_language
        in ARABIC_FAMILY
        else None
    )

    non_english_scores = {
        "ur": 0.0,
        "pa_shah": 0.0,
        "ps": 0.0,
        "sd": 0.0,
        "ar": 0.0,
    }


    # --------------------------------------------------------
    # SHORT ACOUSTIC PROBES
    # --------------------------------------------------------

    # Punjabi-English switches can happen around a single
    # English medical term such as "heartburn".
    #
    # 1.2 s gives enough phonetic context while retaining
    # useful switch boundaries.
    probe_seconds = 1.20
    minimum_tail = 0.45

    probes = []


    def display_probability(
        probs: dict[str, float],
        language: str,
    ) -> float:

        if language == "pa_shah":
            # Pakistani Punjabi/Shahmukhi is acoustically very
            # close to Urdu/Hindi. In our real recordings the
            # Whisper language detector often places Punjabi
            # probability under hi/ur rather than pa.
            #
            # These probabilities are used ONLY to decide
            # Punjabi-vs-English acoustic regions.
            #
            # They do NOT permit Hindi/Devanagari output.
            # Final Punjabi transcription is still validated
            # and displayed as Shahmukhi only.
            return max(
                probs.get("pa", 0.0),

                0.95
                * probs.get("ur", 0.0),

                0.90
                * probs.get("hi", 0.0),
            )

        if language == "ur":
            return max(
                probs.get("ur", 0.0),
                0.90
                * probs.get("hi", 0.0),
            )

        return probs.get(
            language,
            0.0,
        )


    for speech in speech_chunks:

        speech_start = max(
            0.0,
            speech["start"]
            / sample_rate,
        )

        speech_end = min(
            audio_duration,
            speech["end"]
            / sample_rate,
        )

        cursor = speech_start

        while cursor < speech_end:

            probe_end = min(
                cursor
                + probe_seconds,
                speech_end,
            )

            if (
                speech_end
                - probe_end
                < minimum_tail
            ):
                probe_end = (
                    speech_end
                )

            if (
                probe_end
                - cursor
                < 0.35
            ):
                break

            clip_start = int(
                cursor
                * sample_rate
            )

            clip_end = int(
                probe_end
                * sample_rate
            )

            clip = audio[
                clip_start:clip_end
            ]

            try:
                (
                    detected,
                    detected_probability,
                    probabilities,
                ) = model.detect_language(
                    audio=clip,
                    vad_filter=False,
                    language_detection_segments=1,
                    language_detection_threshold=0.0,
                )

                probs = (
                    _language_probability_map(
                        probabilities
                    )
                )

            except Exception as exc:

                logger.warning(
                    "Acoustic language probe failed "
                    "%.2f-%.2f: %s",
                    cursor,
                    probe_end,
                    exc,
                )

                detected = (
                    preferred_primary
                    or "ur"
                )

                detected_probability = 0.0
                probs = {}


            duration = (
                probe_end
                - cursor
            )

            # Build consultation-wide non-English evidence.
            for candidate in (
                "ur",
                "pa_shah",
                "ps",
                "sd",
                "ar",
            ):
                non_english_scores[
                    candidate
                ] += (
                    display_probability(
                        probs,
                        candidate,
                    )
                    * duration
                )


            probes.append(
                {
                    "start":
                        cursor,

                    "end":
                        probe_end,

                    "detected":
                        detected,

                    "detected_probability":
                        float(
                            detected_probability
                            or 0.0
                        ),

                    "probabilities":
                        probs,
                }
            )

            cursor = (
                probe_end
            )


    if not probes:
        return []


    # --------------------------------------------------------
    # PICK DOMINANT NON-ENGLISH LANGUAGE
    # --------------------------------------------------------

    if preferred_primary:

        dominant_non_english = (
            preferred_primary
        )

    else:

        dominant_non_english = max(
            non_english_scores,
            key=non_english_scores.get,
        )


    # --------------------------------------------------------
    # CLASSIFY EACH PROBE AS:
    #
    #   ENGLISH
    #       or
    #   DOMINANT NON-ENGLISH LANGUAGE
    #
    # We intentionally avoid allowing random languages to
    # enter the transcript.
    # --------------------------------------------------------

    classified = []

    for probe in probes:

        probs = probe[
            "probabilities"
        ]

        english_probability = (
            probs.get(
                "en",
                0.0,
            )
        )

        primary_probability = (
            display_probability(
                probs,
                dominant_non_english,
            )
        )

        detected = probe[
            "detected"
        ]


        # Strong English acoustic evidence.
        # Punjabi-English needs a relatively sensitive
        # English detector because individual English medical
        # terms such as "heartburn" may occur inside Punjabi.
        #
        # Urdu-English is acoustically more stable and uses a
        # stricter threshold to avoid stealing Urdu words such
        # as "کھانسی اور بخار" into an English region.
        if dominant_non_english == "pa_shah":

            english_threshold = 0.42
            english_margin = 0.05
            detected_english_threshold = 0.42

        else:

            english_threshold = 0.62
            english_margin = 0.08
            detected_english_threshold = 0.55


        english = bool(
            (
                english_probability
                >= english_threshold
                and
                english_probability
                >= primary_probability
                + english_margin
            )
            or (
                detected == "en"
                and
                english_probability
                >= detected_english_threshold
                and
                english_probability
                >= primary_probability
            )
        )


        if english:
            language = "en"
            confidence = (
                english_probability
            )

        else:
            language = (
                dominant_non_english
            )
            confidence = (
                primary_probability
            )


        classified.append(
            {
                "start":
                    probe["start"],

                "end":
                    probe["end"],

                "language":
                    language,

                "language_confidence":
                    float(
                        confidence
                    ),

                "acoustic_language":
                    detected,

                "language_candidates":
                    sorted(
                        [
                            [
                                str(k),
                                round(
                                    float(v),
                                    6,
                                ),
                            ]
                            for k, v
                            in probs.items()
                        ],
                        key=lambda item:
                            item[1],
                        reverse=True,
                    )[:5],

                "needs_review":
                    bool(
                        confidence
                        < 0.60
                    ),
            }
        )


    # --------------------------------------------------------
    # REMOVE ISOLATED LOW-CONFIDENCE LANGUAGE SPIKES
    # --------------------------------------------------------

    if len(classified) >= 3:

        for i in range(
            1,
            len(classified) - 1,
        ):

            previous = (
                classified[i - 1]
            )

            current = (
                classified[i]
            )

            following = (
                classified[i + 1]
            )

            if (
                previous["language"]
                == following["language"]
                and
                current["language"]
                != previous["language"]
                and
                current[
                    "language_confidence"
                ]
                < 0.45
            ):
                current[
                    "language"
                ] = previous[
                    "language"
                ]

                current[
                    "needs_review"
                ] = True


    # --------------------------------------------------------
    # MERGE ADJACENT WINDOWS OF SAME LANGUAGE
    # --------------------------------------------------------

    regions = []

    for probe in classified:

        if (
            regions
            and
            regions[-1]["language"]
            == probe["language"]
            and
            probe["start"]
            - regions[-1]["end"]
            <= 0.35
        ):

            regions[-1]["end"] = (
                probe["end"]
            )

            regions[-1][
                "language_confidence"
            ] = min(
                regions[-1][
                    "language_confidence"
                ],
                probe[
                    "language_confidence"
                ],
            )

            regions[-1][
                "needs_review"
            ] = bool(
                regions[-1].get(
                    "needs_review",
                    False,
                )
                or probe.get(
                    "needs_review",
                    False,
                )
            )

        else:

            regions.append(
                dict(
                    probe
                )
            )


    # --------------------------------------------------------
    # PUNJABI SHORT-ENGLISH-ISLAND SAFETY
    # --------------------------------------------------------

    if (
        dominant_non_english
        == "pa_shah"
        and len(regions) >= 3
    ):

        for i in range(
            1,
            len(regions) - 1,
        ):

            previous = regions[
                i - 1
            ]

            current = regions[
                i
            ]

            following = regions[
                i + 1
            ]

            current_duration = (
                current["end"]
                - current["start"]
            )


            if (
                previous["language"]
                == "pa_shah"
                and
                current["language"]
                == "en"
                and
                following["language"]
                == "pa_shah"
                and
                current_duration
                <= 2.60
            ):

                current[
                    "language"
                ] = "pa_shah"

                # Boundary uncertainty is clinically relevant.
                current[
                    "needs_review"
                ] = True

                current[
                    "short_english_island_collapsed"
                ] = True


        # Re-merge regions after any relabelling above.
        remerged = []

        for region in regions:

            if (
                remerged
                and
                remerged[-1][
                    "language"
                ]
                == region[
                    "language"
                ]
                and
                (
                    region[
                        "start"
                    ]
                    - remerged[
                        -1
                    ][
                        "end"
                    ]
                )
                <= 0.35
            ):

                previous = (
                    remerged[-1]
                )

                previous[
                    "end"
                ] = region[
                    "end"
                ]

                previous[
                    "language_confidence"
                ] = min(
                    previous.get(
                        "language_confidence",
                        1.0,
                    ),
                    region.get(
                        "language_confidence",
                        1.0,
                    ),
                )

                previous[
                    "needs_review"
                ] = bool(
                    previous.get(
                        "needs_review",
                        False,
                    )
                    or region.get(
                        "needs_review",
                        False,
                    )
                )

                previous[
                    "short_english_island_collapsed"
                ] = bool(
                    previous.get(
                        "short_english_island_collapsed",
                        False,
                    )
                    or region.get(
                        "short_english_island_collapsed",
                        False,
                    )
                )

            else:

                remerged.append(
                    dict(
                        region
                    )
                )


        regions = remerged


    # --------------------------------------------------------
    # FORCE-DECODE EACH LANGUAGE REGION
    # --------------------------------------------------------

    final_segments = []

    for region in regions:

        # Absolute physical protection.
        region["start"] = max(
            0.0,
            min(
                region["start"],
                audio_duration,
            ),
        )

        region["end"] = max(
            region["start"],
            min(
                region["end"],
                audio_duration,
            ),
        )

        if (
            region["end"]
            - region["start"]
            < 0.15
        ):
            continue

        region[
            "fallback_text"
        ] = ""

        region[
            "timestamp_clamped"
        ] = False

        decoded = (
            _transcribe_language_region(
                model,
                audio,
                sample_rate,
                region,
            )
        )

        decoded[
            "needs_review"
        ] = bool(
            decoded.get(
                "needs_review",
                False,
            )
            or region.get(
                "needs_review",
                False,
            )
            or not decoded.get(
                "script_valid",
                True,
            )
        )

        final_segments.append(
            decoded
        )


    return _dedupe_segments(
        final_segments
    )


# === PHASE17 ACOUSTIC CODE-SWITCH END ===

# This is the main STT entry point used by the consultation pipeline. It runs the
# initial Whisper pass to establish the dominant language, applies the segmented
# acoustic route when automatic language detection or Shahmukhi Punjabi requires
# it, removes duplicate segments, identifies code-switching, optionally attaches
# speaker labels and finally marks uncertain segments for doctor review before
# returning the complete transcript and STT metadata.

def transcribe(
    audio_path: str | Path,
    primary_language:
        Optional[str] = None,
    secondary_language:
        Optional[str] = None,
) -> dict:

    # --------------------------------------------------------
    # INITIAL PASS
    # --------------------------------------------------------
    #
    # The first pass supplies reliable speech boundaries and
    # the dominant whole-consultation language.
    # --------------------------------------------------------

    automatic_mode = (
        primary_language
        is None
    )

    # Pakistani Punjabi must also use the segmented
    # detect-first/decode-second route even when the caller
    # explicitly supplies pa_shah.
    #
    # The standard Whisper Punjabi decoder can emit Gurmukhi,
    # Devanagari, Romanised Punjabi or unrelated scripts.
    # Our Punjabi route instead compares Punjabi and Urdu
    # decoder candidates and exposes Shahmukhi only.
    segmented_language_mode = (
        automatic_mode
        or primary_language == "pa_shah"
    )


    # The base pass determines the dominant consultation
    # language only. Mixed-language transcription is handled
    # separately using physical VAD + acoustic detection +
    # forced language-region decoding.
    #
    # Do NOT use faster-whisper multilingual transcript text
    # as the source of the clinical transcript.
    base_result = _run_pass(
        audio_path,
        primary_language,
        multilingual=False,
    )


    dominant_language = (
        primary_language
        or base_result.get(
            "language"
        )
        or "en"
    )


    # --------------------------------------------------------
    # SEGMENT-LEVEL ACOUSTIC LANGUAGE DETECTION
    # --------------------------------------------------------

    if (
        segmented_language_mode
        and base_result.get(
            "segments"
        )
    ):

        segments = (
            _acoustic_code_switch_transcription(
                audio_path,
                base_result,
                dominant_language,
                secondary_language,
            )
        )

    else:

        segments = (
            _dedupe_segments(
                base_result.get(
                    "segments"
                )
                or []
            )
        )


    # --------------------------------------------------------
    # LANGUAGES PRESENT
    # --------------------------------------------------------

    # Determine all languages represented in the final
    # transcript. This also detects genuine English/Latin
    # phrases embedded inside a segment whose acoustic
    # language label remains Urdu/Punjabi/etc.
    languages = _detected_languages(
        segments,
        dominant_language,
    )


    code_switched = (
        len(
            languages
        )
        > 1
    )


    # --------------------------------------------------------
    # OPTIONAL DIARISATION
    # --------------------------------------------------------

    turns = diarize(
        audio_path
    )

    if turns:

        segments = (
            attach_speakers(
                segments,
                turns,
            )
        )


    # --------------------------------------------------------
    # REVIEW FLAGS
    # --------------------------------------------------------

    for segment in segments:

        avg = segment.get(
            "avg_logprob"
        )

        no_speech = (
            segment.get(
                "no_speech_prob"
            )
        )

        confidence = (
            segment.get(
                "confidence"
            )
        )

        segment[
            "needs_review"
        ] = bool(
            segment.get(
                "needs_review",
                False,
            )
            or (
                avg is not None
                and avg
                < settings.STT_LOW_CONFIDENCE_LOGPROB
            )
            or (
                no_speech is not None
                and no_speech
                > settings.STT_NO_SPEECH_THRESHOLD
            )
            or (
                confidence is not None
                and confidence < 0.70
            )
            or not segment.get(
                "script_valid",
                True,
            )
        )


    transcript_text = " ".join(
        (
            segment.get(
                "text"
            )
            or ""
        ).strip()

        for segment
        in segments

        if (
            segment.get(
                "text"
            )
            or ""
        ).strip()
    ).strip()


    secondary_detected = next(
        (
            language

            for language
            in sorted(
                languages
            )

            if language
            != dominant_language
        ),
        None,
    )


    return {
        "text":
            transcript_text,

        "language":
            dominant_language,

        "primary_language":
            dominant_language,

        "secondary_language":
            secondary_detected,

        "language_confidence":
            base_result.get(
                "language_probability"
            ),

        "languages_detected":
            sorted(
                languages
            ),

        "duration":
            base_result.get(
                "duration"
            ),

        "code_switched":
            code_switched,

        "code_switch_requested":
            bool(
                secondary_language
            ),

        "code_switch_auto_attempted":
            automatic_mode,

        "multilingual_supported":
            bool(
                base_result.get(
                    "multilingual_supported"
                )
            ),

        "multilingual_used":
            bool(
                base_result.get(
                    "multilingual_used"
                )
            ),

        "segment_language_detection":
            segmented_language_mode,

        "segments":
            segments,

        "diarization_available":
            bool(
                turns
            ),
    }


