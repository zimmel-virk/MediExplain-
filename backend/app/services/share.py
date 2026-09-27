"""
Share-link generation.

We don't integrate with the WhatsApp Business API directly (it requires a
verified business account, which is out of academic scope). Instead we:

  1. Generate a signed, short-lived share token for the consultation.
  2. Build a deep link the doctor can tap on their phone: clicking it opens
     WhatsApp with the link pre-filled to the patient's number.
  3. The patient opens the link in any browser to view the summary, listen to
     the audio, and download the PDF — all without needing an account.

This is the realistic offline-friendly delivery model used by many Pakistani
clinics already: doctor messages the patient on WhatsApp, patient taps a link.

The token uses the existing JWT infrastructure with a custom "share" scope so
it's restricted to read-only access to one specific consultation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from jose import jwt

from app.core.config import settings

# This creates a temporary JWT for one consultation only. The custom share scope,
# consultation ID and expiry time keep the public link separate from a normal
# authenticated user session and limit what the token can be used to access.

def make_share_token(consultation_id: int) -> str:
    """Create a short-lived, scope-restricted token for a single consultation."""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.SHARE_TOKEN_EXPIRE_HOURS)
    payload = {
        "scope": "share",
        "consultation_id": consultation_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALG)

# This validates the signature and expiry of the supplied JWT and then checks
# that it is specifically a consultation share token before returning the
# consultation it is allowed to access.

def verify_share_token(token: str) -> int:
    """Returns the consultation_id this token authorises, or raises."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALG])
    if payload.get("scope") != "share":
        raise ValueError("Not a share token")
    cid = payload.get("consultation_id")
    if not cid:
        raise ValueError("Missing consultation_id")
    return int(cid)

# This combines the signed consultation token with the public MediExplain+ URL
# to produce the browser link that can be sent to the patient.
def share_url(consultation_id: int) -> str:
    token = make_share_token(consultation_id)
    return f"{settings.PUBLIC_BASE_URL}/share/{token}"


# This builds the WhatsApp deep link used by the doctor to share the released
# consultation. The patient receives a language-specific message containing the
# temporary consultation URL, while an optional phone number can open the message
# directly for that recipient instead of showing WhatsApp's recipient picker.
def whatsapp_link(consultation_id: int, phone: str | None = None,
                  patient_name: str | None = None,
                  language: str = "en") -> str:
    """
    Build a wa.me URL that opens WhatsApp with a pre-filled message.

    `phone` should be E.164 without the leading '+' (e.g. "923001234567").
    Omitting `phone` gives a "choose recipient" picker on tap.
    """
    url = share_url(consultation_id)
    greeting_by_lang = {
        "en": f"Hello{' ' + patient_name if patient_name else ''}, here is your "
              f"care summary from your doctor: {url}",
        "ur": f"السلام علیکم{' ' + patient_name if patient_name else ''}، "
              f"آپ کی ڈاکٹر کی طرف سے علاج کا خلاصہ: {url}",
        "ar": f"مرحبا{' ' + patient_name if patient_name else ''}، "
              f"هذا ملخص الرعاية الصحية من طبيبك: {url}",
        "pa": f"ਸਤ ਸ੍ਰੀ ਅਕਾਲ{' ' + patient_name if patient_name else ''}, "
              f"ਤੁਹਾਡੇ ਡਾਕਟਰ ਦੀ ਦੇਖਭਾਲ ਦਾ ਸਾਰ: {url}",
    }
    text = greeting_by_lang.get(language, greeting_by_lang["en"])
    encoded = quote(text)

    if phone:
        # Strip +, spaces, dashes
        cleaned = "".join(ch for ch in phone if ch.isdigit())
        return f"https://wa.me/{cleaned}?text={encoded}"
    return f"https://wa.me/?text={encoded}"
