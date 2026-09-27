"""Optional local speaker diarisation using pyannote.audio."""
from __future__ import annotations
import logging
from pathlib import Path
from app.core.config import settings

logger = logging.getLogger(__name__)
_pipeline = None

# This file handles optional speaker diarisation for consultation recordings.
# It uses the configured pyannote.audio diarisation model to identify when
# different speakers are active in the audio, then matches those speaker turns
# with the transcript segments. The model is loaded only when diarisation is
# enabled and a Hugging Face token is available, and the loaded pipeline is
# reused instead of being initialised again for every consultation.


# This check makes sure speaker diarisation is only attempted when it has been
# enabled in the application settings and the required Hugging Face token exists.
def available() -> bool:
    return bool(settings.DIARIZATION_ENABLED and settings.HF_TOKEN)


# This function loads the configured pyannote.audio speaker diarisation model.
# The AI model analyses the audio to separate portions spoken by different
# speakers. Once loaded, the pipeline is cached in memory so later recordings
# can reuse the same model without loading it again.
def _load_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    if not available():
        return None
    from pyannote.audio import Pipeline
    # pyannote versions have used both token= and use_auth_token=. Support both.
    try:
        _pipeline = Pipeline.from_pretrained(settings.DIARIZATION_MODEL, token=settings.HF_TOKEN)
    except TypeError:
        _pipeline = Pipeline.from_pretrained(
            settings.DIARIZATION_MODEL, use_auth_token=settings.HF_TOKEN
        )
    return _pipeline


# This function runs the diarisation model on an audio recording and converts
# its output into simple speaker turns containing a start time, end time and
# speaker label. If diarisation fails, the rest of the consultation workflow
# can continue without speaker information.
def diarize(audio_path: str | Path) -> list[dict]:
    pipe = _load_pipeline()
    if pipe is None:
        return []
    try:
        output = pipe(str(audio_path))
        turns = []
        diarization = getattr(output, "speaker_diarization", output)
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append({
                "start": float(turn.start),
                "end": float(turn.end),
                "speaker": str(speaker),
            })
        return turns
    except Exception as exc:
        logger.warning("Diarization failed: %s", exc)
        return []


# This function links the detected speaker turns back to the transcript. Each
# transcript segment is assigned the speaker with the greatest time overlap,
# while the proportion of the segment covered by that speaker is stored as the
# diarisation confidence value.
def attach_speakers(segments: list[dict], turns: list[dict]) -> list[dict]:
    for seg in segments:
        s0, s1 = float(seg.get("start", 0)), float(seg.get("end", 0))
        best, best_overlap = None, 0.0
        for turn in turns:
            overlap = max(0.0, min(s1, turn["end"]) - max(s0, turn["start"]))
            if overlap > best_overlap:
                best_overlap, best = overlap, turn["speaker"]
        seg["speaker"] = best
        seg["diarization_confidence"] = (
            round(best_overlap / max(0.001, s1 - s0), 3) if best else None
        )
    return segments
