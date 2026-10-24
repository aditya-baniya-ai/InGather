from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.auth import me_out
from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.schemas import DemoVerifyIn, MeOut, StripeStartOut, VerificationOut
from app.security import current_user, not_found
from app.services.identity import IdentityService

router = APIRouter(prefix="/api", tags=["verification"])


async def raw_body(request: Request) -> bytes:
    """Signature verification needs the exact bytes Stripe signed."""
    return await request.body()


@router.get("/verification", response_model=VerificationOut)
def get_verification(user: User = Depends(current_user), db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    return IdentityService(db, s).status(user)


@router.post("/verification/demo", response_model=MeOut)
def verify_demo(
    body: DemoVerifyIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings),
):
    if not s.demo_mode:
        raise not_found()
    IdentityService(db, s).verify_demo(user)
    return me_out(user, db, s)


@router.post("/verification/stripe/start", response_model=StripeStartOut)
def stripe_start(user: User = Depends(current_user), db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    return {"url": IdentityService(db, s).start_stripe(user)}


@router.post("/webhooks/stripe")
def stripe_webhook(
    body: bytes = Depends(raw_body),
    stripe_signature: str | None = Header(None),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings),
):
    IdentityService(db, s).handle_webhook(body, stripe_signature)
    return {"received": True}
