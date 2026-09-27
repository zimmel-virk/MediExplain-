"""FastAPI entrypoint for MediExplain+ Final."""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import assistant_reviews, auth, consultations, cross_check, learning, medications, schedules, share, support, users
from app.core.config import settings
from app.core.database import init_db

# This is the main FastAPI entrypoint for MediExplain+. It creates the application,
# applies the configured CORS policy, registers the API routers for authentication,
# consultations, medication workflows, cross-checking, support and learning features,
# and initializes the database when the backend starts. It also exposes lightweight
# health and language endpoints used by the frontend and deployment checks.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Secure multilingual AI consultation summariser. Academic research prototype — not a medical device.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(consultations.router)
app.include_router(cross_check.router)
app.include_router(medications.router)
app.include_router(schedules.router)
app.include_router(share.router)
app.include_router(assistant_reviews.router)
app.include_router(support.router)
app.include_router(learning.router)

@app.on_event("startup")
async def on_startup():
    await init_db()

@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}

@app.get("/api/languages")
async def languages():
    return [
        {
            "code": k,
            "name": v["name"],
            "native": v.get("native", v["name"]),
            "has_tts": bool(v.get("tts")),
            "rtl": v.get("rtl", False),
            # Quality is intentionally described as "evaluation pending" until
            # measured on the final test set; no fabricated confidence labels.
            "quality": v.get("quality", "evaluation_pending"),
        }
        for k, v in settings.SUPPORTED_LANGUAGES.items()
    ]
