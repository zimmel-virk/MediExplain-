"""Grounding checks using DeBERTa-v3 NLI.

This is an assistive warning layer, not a clinical decision maker. If the model
is unavailable, the system records the check as unavailable and still requires
human doctor approval.
"""
from __future__ import annotations
import logging
import re
from functools import lru_cache
from typing import Iterable
from app.core.config import settings

logger = logging.getLogger(__name__)
_model = None
_tokenizer = None


# This function loads the configured DeBERTa-v3 Natural Language Inference model
# and its tokenizer from Hugging Face. The model is used to compare a generated
# clinical statement with evidence from the consultation transcript and estimate
# whether the transcript supports, contradicts or does not clearly support that
# statement. The loaded model is kept in memory so it can be reused for later
# grounding checks instead of being loaded again for every claim.
def _load():
    global _model, _tokenizer
    if _model is not None:
        return _tokenizer, _model
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    _tokenizer = AutoTokenizer.from_pretrained(
        settings.NLI_MODEL, cache_dir=settings.MODEL_CACHE_DIR
    )
    _model = AutoModelForSequenceClassification.from_pretrained(
        settings.NLI_MODEL, cache_dir=settings.MODEL_CACHE_DIR
    )
    _model.eval()
    return _tokenizer, _model


# This helper separates longer transcript or summary text into individual
# sentences so generated claims can be checked against transcript evidence
# one statement at a time.
def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip(" -*•\t") for p in parts if len(p.strip()) >= 8]


# This function performs one DeBERTa-v3 NLI comparison between transcript
# evidence and a generated claim. The transcript text is treated as the premise
# and the generated statement as the hypothesis. The model returns probabilities
# for entailment, contradiction and neutral, which are then converted into the
# project's simpler entailed, contradiction or unsupported result using the
# configured safety thresholds.
def check_pair(premise: str, hypothesis: str) -> dict:
    try:
        import torch
        tok, model = _load()
        batch = tok(
            premise, hypothesis, truncation=True, max_length=512,
            return_tensors="pt"
        )
        with torch.no_grad():
            probs = torch.softmax(model(**batch).logits[0], dim=-1).tolist()
        labels = {int(k): str(v).lower() for k, v in model.config.id2label.items()}
        scores = {labels.get(i, str(i)): float(p) for i, p in enumerate(probs)}
        # Normalise common label spelling.
        entail = max((v for k,v in scores.items() if "entail" in k), default=0.0)
        contradiction = max((v for k,v in scores.items() if "contrad" in k), default=0.0)
        neutral = max((v for k,v in scores.items() if "neutral" in k), default=0.0)
        if entail >= settings.NLI_ENTAILMENT_THRESHOLD:
            label = "entailed"
        elif contradiction >= settings.NLI_CONTRADICTION_THRESHOLD:
            label = "contradiction"
        else:
            label = "unsupported"
        return {
            "available": True,
            "label": label,
            "entailment": round(entail, 4),
            "contradiction": round(contradiction, 4),
            "neutral": round(neutral, 4),
        }
    except Exception as exc:
        logger.warning("NLI unavailable: %s", exc)
        return {"available": False, "label": "unavailable", "error": str(exc)}


# This function checks each generated summary claim against the consultation
# transcript. Before running the NLI model, it ranks transcript segments by
# simple word overlap and sends only the most relevant evidence candidates to
# DeBERTa-v3, which avoids running the model unnecessarily across every segment.
# For each claim, the evidence with the strongest entailment score is retained.
# These results are used as an assistive grounding warning layer for doctor
# review rather than automatically deciding whether clinical content is correct.

def ground_summary(transcript: str, summary: str, transcript_segments: Iterable[str] | None = None) -> list[dict]:
    """Find best transcript evidence for each generated claim."""
    evidence_units = [x for x in (transcript_segments or []) if x and x.strip()]
    if not evidence_units:
        evidence_units = _sentences(transcript)
    if not evidence_units:
        evidence_units = [transcript or ""]

    results = []
    for claim in _sentences(summary):
        best = None
        # NLI on every segment can be expensive. First rank lexical overlap and
        # test up to the six most relevant evidence units.
        claim_words = set(re.findall(r"\w+", claim.lower()))
        ranked = sorted(
            evidence_units,
            key=lambda s: len(claim_words & set(re.findall(r"\w+", s.lower()))),
            reverse=True,
        )[:6]
        for ev in ranked:
            score = check_pair(ev, claim)
            candidate = {**score, "statement": claim, "evidence": ev}
            if not best or candidate.get("entailment", 0) > best.get("entailment", 0):
                best = candidate
            if candidate.get("label") == "entailed":
                break
        results.append(best or {"statement": claim, "label": "unavailable", "available": False})
    return results
