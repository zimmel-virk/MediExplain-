"""Lightweight PII helpers — names, phones, IDs scrubbed before research use."""
import re

PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
CNIC_RE = re.compile(r"\b\d{5}-\d{7}-\d\b")  # Pakistani national ID format


def anonymise(text: str) -> str:
    """Strip obvious PII for research/export use. Not bulletproof — names need NER."""
    if not text:
        return text
    text = PHONE_RE.sub("[PHONE]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = CNIC_RE.sub("[CNIC]", text)
    return text
