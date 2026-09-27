"""Optional Meta WhatsApp Cloud API PDF delivery.

This is an additive delivery adapter only. It never creates or modifies clinical
content. The exact same released patient PDF generator used by the portal is
called before these bytes are uploaded. Credentials must be supplied through
environment variables; nothing sensitive is stored in source code or the
browser.
"""
from __future__ import annotations

import re
import httpx

from app.core.config import settings

# This file provides the optional WhatsApp Cloud API delivery route for released
# MediExplain+ patient PDFs. It checks that the required server-side credentials
# are configured, normalises the patient's phone number into the format expected
# by WhatsApp, uploads the existing released PDF as document media and then sends
# that document to the selected recipient. The adapter only handles delivery;
# clinical content and PDF generation are completed elsewhere before this stage.

def configured() -> bool:
    return bool(
        settings.WHATSAPP_ENABLED
        and settings.WHATSAPP_PHONE_NUMBER_ID
        and settings.WHATSAPP_ACCESS_TOKEN
    )


def normalise_phone(phone: str | None) -> str:
    raw = str(phone or "").strip()
    if not raw:
        raise ValueError("Patient WhatsApp number is missing")
    digits = re.sub(r"\D", "", raw)
    # E.164-compatible practical length guard. The Cloud API receives digits only.
    if len(digits) < 8 or len(digits) > 15:
        raise ValueError("Patient WhatsApp number must use international format, e.g. +923001234567")
    return digits


async def send_pdf(phone: str, pdf_bytes: bytes, filename: str, caption: str) -> dict:
    if not configured():
        raise RuntimeError(
            "WhatsApp Cloud API is not configured. Set WHATSAPP_ENABLED=true, "
            "WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN in backend/.env."
        )
    recipient = normalise_phone(phone)
    version = settings.WHATSAPP_API_VERSION.strip() or "v23.0"
    base = f"https://graph.facebook.com/{version}/{settings.WHATSAPP_PHONE_NUMBER_ID}"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"}

    timeout = httpx.Timeout(45.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        upload = await client.post(
            f"{base}/media",
            headers=headers,
            data={"messaging_product": "whatsapp", "type": "application/pdf"},
            files={"file": (filename, pdf_bytes, "application/pdf")},
        )
        upload.raise_for_status()
        media_id = upload.json().get("id")
        if not media_id:
            raise RuntimeError("WhatsApp media upload did not return a media id")

        send = await client.post(
            f"{base}/messages",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "document",
                "document": {
                    "id": media_id,
                    "filename": filename,
                    "caption": caption[:1024],
                },
            },
        )
        send.raise_for_status()
        body = send.json()
        message_id = None
        messages = body.get("messages") or []
        if messages:
            message_id = messages[0].get("id")
        return {"message_id": message_id, "recipient": recipient, "media_id": media_id}
