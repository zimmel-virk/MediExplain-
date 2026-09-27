"""
Central configuration for MediExplain+ Final.

All settings can be overridden with environment variables or backend/.env.
Runtime paths are rooted at the backend directory and database records store
portable relative storage references rather than machine-specific absolute paths.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        extra="ignore",
        case_sensitive=True,
    )

    APP_NAME: str = "MediExplain+"
    APP_VERSION: str = "1.0.0-final"
    DEBUG: bool = True

    # Security. scripts/bootstrap.py creates a random value in .env.
    SECRET_KEY: str = "DEV_ONLY_CHANGE_ME"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8
    SHARE_TOKEN_EXPIRE_HOURS: int = 24 * 7

    AUTH_MODE: str = "local"
    AWS_REGION: str = "ap-south-1"
    COGNITO_USER_POOL_ID: str = ""
    COGNITO_CLIENT_ID: str = ""
    MFA_FERNET_KEY: str = ""

    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'mediexplain.db'}"
    DATA_DIR: Path = BASE_DIR / "data"
    UPLOAD_DIR: Path = BASE_DIR / "data" / "uploads"
    AUDIO_CACHE_DIR: Path = BASE_DIR / "audio_cache"
    MODEL_CACHE_DIR: Path = BASE_DIR / "data" / "model_cache"
    MEDICATION_DB_PATH: Path = BASE_DIR / "data" / "mediexplain.db"

    # STT
    WHISPER_MODEL: str = "medium"
    WHISPER_DEVICE: str = "auto"
    WHISPER_COMPUTE_TYPE: str = "int8"
    STT_LOW_CONFIDENCE_LOGPROB: float = -0.5
    STT_NO_SPEECH_THRESHOLD: float = 0.6
    WHISPER_BEAM_SIZE: int = 5

    # Optional speaker diarisation.
    DIARIZATION_ENABLED: bool = True
    DIARIZATION_MODEL: str = "pyannote/speaker-diarization-3.1"
    HF_TOKEN: str | None = None

    # Local LLM
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_TIMEOUT_SECONDS: int = 240
    OLLAMA_NUM_CTX: int = 4096

    # NLI safety checker
    NLI_ENABLED: bool = True
    NLI_MODEL: str = "cross-encoder/nli-deberta-v3-base"
    NLI_ENTAILMENT_THRESHOLD: float = 0.55
    NLI_CONTRADICTION_THRESHOLD: float = 0.45

    # Translation
    NLLB_MODEL: str = "facebook/nllb-200-distilled-600M"
    TRANSLATION_SEMANTIC_THRESHOLD: float = 0.55

    # OCR
    OCR_LANGS: str = "eng+urd"
    OCR_MAX_UPLOAD_MB: int = 8
    OCR_ENGINE: str = "auto"  # auto | tesseract | paddle
    OCR_LOW_CONFIDENCE: float = 0.60

    # Medication terminology
    RXNORM_PRESCRIBABLE_URL: str = (
        "https://download.nlm.nih.gov/rxnorm/"
        "RxNorm_full_prescribe_08032026.zip"
    )
    MEDICATION_CANDIDATE_THRESHOLD: float = 0.72
    MEDICATION_MIN_MATCH_SCORE: float = 0.72
    MEDICATION_AUTO_ACCEPT_SCORE: float = 0.96
    MEDICATION_MAX_RESULTS: int = 10

    # Delivery
    PUBLIC_BASE_URL: str = "http://localhost:5173"
    DEFAULT_TIMEZONE: str = "Asia/Karachi"
    ALLOW_CLOUD_TTS_FALLBACK: bool = False

    # Optional direct PDF delivery through Meta WhatsApp Cloud API.
    # Disabled by default; credentials belong in backend/.env / secret storage.
    WHATSAPP_ENABLED: bool = False
    WHATSAPP_API_VERSION: str = "v23.0"
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""

    # Browser-origin development CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    SUPPORTED_LANGUAGES: dict = {
        "en": {
            "name": "English", "native": "English",
            "nllb": "eng_Latn", "whisper": "en",
            "tts": "eng", "rtl": False,
        },
        "ur": {
            "name": "Urdu", "native": "اردو",
            "nllb": "urd_Arab", "whisper": "ur",
            "tts": "urd-script_arabic", "rtl": True,
        },
        "ar": {
            "name": "Arabic", "native": "العربية",
            "nllb": "arb_Arab", "whisper": "ar",
            "tts": "ara", "rtl": True,
        },
        "pa_shah": {
            "name": "Punjabi (Shahmukhi)", "native": "پنجابی",
            "nllb": "pan_Guru", "whisper": "pa",
            "tts": "pan", "shahmukhi": True, "rtl": True,
        },
        
        "ps": {
            "name": "Pashto", "native": "پښتو",
            "nllb": "pbt_Arab", "whisper": "ps",
            "tts": "pus", "rtl": True,
        },
        "sd": {
            "name": "Sindhi", "native": "سنڌي",
            "nllb": "snd_Arab", "whisper": "sd",
            "tts": "snd", "rtl": True,
        },
    }

    @property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.CORS_ORIGINS.split(",") if x.strip()]

settings = Settings()

for path in (
    settings.DATA_DIR,
    settings.UPLOAD_DIR,
    settings.AUDIO_CACHE_DIR,
    settings.MODEL_CACHE_DIR,
):
    path.mkdir(parents=True, exist_ok=True)

if not settings.DEBUG and settings.SECRET_KEY == "DEV_ONLY_CHANGE_ME":
    raise RuntimeError(
        "SECRET_KEY must be configured before running MediExplain+ with DEBUG=false."
    )
