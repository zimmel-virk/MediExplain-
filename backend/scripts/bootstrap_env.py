#!/usr/bin/env python3
"""Create backend/.env without overwriting an existing configuration."""
from pathlib import Path
import secrets

# This setup helper creates the backend environment file for a fresh local
# MediExplain+ installation. It preserves any existing configuration, otherwise
# generates a random application secret and writes the default model, database,
# language, TTS, WhatsApp and frontend connection settings needed to start the
# project locally.

BACKEND = Path(__file__).resolve().parents[1]
env = BACKEND / ".env"

if env.exists():
    print(f"Existing {env.name} preserved.")
else:
    secret = secrets.token_urlsafe(48)
    env.write_text(
        "DEBUG=true\n"
        f"SECRET_KEY={secret}\n"
        "OLLAMA_MODEL=llama3.1:8b\n"
        "WHISPER_MODEL=medium\n"
        "DIARIZATION_ENABLED=true\n"
        "HF_TOKEN=\n"
        "NLI_ENABLED=true\n"
        "OCR_ENGINE=auto\n"
        "DEFAULT_TIMEZONE=Asia/Karachi\n"
        "ALLOW_CLOUD_TTS_FALLBACK=false\n"
        "WHATSAPP_ENABLED=false\n"
        "WHATSAPP_API_VERSION=v23.0\n"
        "WHATSAPP_PHONE_NUMBER_ID=\n"
        "WHATSAPP_ACCESS_TOKEN=\n"
        "PUBLIC_BASE_URL=http://localhost:5173\n"
        "CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173\n"
    )
    print(f"Created {env} with a random SECRET_KEY.")
