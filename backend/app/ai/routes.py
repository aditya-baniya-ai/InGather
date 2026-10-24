"""AI extras: plan intake drafts, voice transcription, plan cover images, and connector tokens for the user's own Muse agent."""

import hashlib
import logging
import secrets
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.ai.muse import MuseClient
from app.ai.orchestra.intake import IntakeAgent
from app.config import Settings, get_settings
from app.db import get_db
from app.models import ConnectorToken, Plan, User, now
from app.schemas import PlanDraftIn, PlanDraftOut
from app.security import current_user
from app.services.ratelimit import limiter

log = logging.getLogger("ingather.ai")
router = APIRouter(prefix="/api", tags=["ai"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024
WAV_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave", "application/octet-stream", ""}
COVER_STYLE = {
    "travel": "a sunny city street scene with landmarks",
    "conference": "a bright modern conference hall lobby",
    "hackathon": "laptops and coffee cups on a long table in a lively hackathon space",
    "study": "an inviting library table with books and warm light",
    "coffee": "a cozy café table with latte art",
    "event": "a festive public event with string lights",
}


def muse(settings: Settings = Depends(get_settings)) -> MuseClient:
    client = MuseClient(settings)
    if not client.ai_live:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ai_unavailable")
    return client


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def owned_plan(db: Session, settings: Settings, user: User, plan_id: uuid.UUID) -> Plan:
    from app.services.policy import Policy

    return Policy(db, settings).own_plan(user, plan_id)


def plan_out(db: Session, settings: Settings, plan: Plan):
    from app.services.plans import Plans

    return Plans(db, settings).out(plan)


def cover_prompt(plan: Plan) -> str:
    """Built ONLY from activity type, city and interests: no names, goal text or other personal data."""
    scene = COVER_STYLE.get(plan.activity_type, "friends meeting at a public place")
    interests = ", ".join(i for i in (plan.interests or [])[:3] if i.replace(" ", "").isalnum())
    return (
        f"Editorial lifestyle photograph of {scene} in {plan.city[:60]}"
        + (f", subtle hints of {interests}" if interests else "")
        + ". Natural light, warm and inviting, shallow depth of field, no recognizable faces, no text, no logos, wide banner composition."
    )


@router.post("/plans/draft", response_model=PlanDraftOut)
def draft_plan(
    body: PlanDraftIn,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    client: MuseClient = Depends(muse),
):
    """Intake agent: free text -> unsaved plan draft. The text is untrusted data; nothing is stored."""
    limiter.hit("plan_draft", user.id)
    try:
        return IntakeAgent(settings, client).draft(body.text, body.timezone_hint)
    except Exception as exc:
        log.warning("plan draft failed: %s", type(exc).__name__)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "draft_failed")


@router.post("/voice/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    user: User = Depends(current_user),
    client: MuseClient = Depends(muse),
):
    if (audio.content_type or "").lower() not in WAV_TYPES and not (audio.filename or "").lower().endswith(".wav"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "wav_required")
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "audio_too_large")
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "wav_required")
    try:
        text = client.transcribe_wav(data)
    except Exception as exc:
        log.warning("transcription failed: %s", type(exc).__name__)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "transcription_failed")
    return {"text": text}


@router.post("/plans/{plan_id}/cover")
def generate_cover(
    plan_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    plan = owned_plan(db, settings, user, plan_id)  # 404 before revealing AI availability
    client = muse(settings)  # 503 ai_unavailable without a key
    try:
        save_cover(db, settings, plan, client)
    except Exception as exc:
        log.warning("cover generation failed: %s", type(exc).__name__)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "image_generation_failed")
    return plan_out(db, settings, plan)


@router.post("/connector/tokens")
def create_connector_token(user: User = Depends(current_user), db: Session = Depends(get_db)):
    token = "igc_" + secrets.token_urlsafe(32)
    db.add(ConnectorToken(user_id=user.id, token_hash=hash_token(token)))
    db.commit()
    return {"token": token}


@router.delete("/connector/tokens", status_code=204)
def revoke_connector_tokens(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(
        update(ConnectorToken)
        .where(ConnectorToken.user_id == user.id, ConnectorToken.revoked_at.is_(None))
        .values(revoked_at=now())
    )
    db.commit()
    return Response(status_code=204)


def save_cover(db: Session, settings: Settings, plan: Plan, client: MuseClient) -> None:
    """Generate a Muse Image cover from non-personal plan attributes and store it under /media."""
    image = client.generate_image(cover_prompt(plan))
    ext = {"png": "png", "jpeg": "jpg", "webp": "webp"}.get(image.fmt, "webp")
    media = Path(settings.media_dir)
    media.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (media / name).write_bytes(image.data)
    plan.cover_image_url = f"/media/{name}"
    db.commit()


def cover_in_background(plan_id: uuid.UUID) -> None:
    """Best-effort cover for a newly created plan; the UI shows the activity photo until it lands."""
    from app.db import SessionLocal

    settings = get_settings()
    with SessionLocal() as db:
        plan = db.get(Plan, plan_id)
        if plan is None or plan.cover_image_url:
            return
        try:
            save_cover(db, settings, plan, MuseClient(settings))
        except Exception as exc:
            log.warning("auto cover failed: %s", type(exc).__name__)
