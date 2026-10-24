"""Identity verification. Stores only status/provider/session id/verified_at/is_adult — never ID data,
never DOB, never secrets. `verified_live` is set only from a signature-verified Stripe webhook and is
never downgraded."""

import hashlib
import hmac
import json
import time
from datetime import date

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import ConsentEvent, User, Verification, now

VERIFIED_EVENT = "identity.verification_session.verified"


def stripe_unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "stripe_unavailable")


def bad_signature() -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_signature")


class StripeIdentity:
    """Thin Stripe Identity adapter over httpx (form-encoded, secret key as Basic auth). No SDK."""

    BASE_URL = "https://api.stripe.com/v1"
    TOLERANCE_SECONDS = 300
    transport: httpx.BaseTransport | None = None  # tests swap in httpx.MockTransport

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def available(self) -> bool:
        return bool(self.settings.stripe_secret_key)

    @property
    def test_mode(self) -> bool:
        return self.settings.stripe_secret_key.startswith("sk_test_")

    def _request(self, method: str, path: str, **kw) -> dict:
        if not self.available:
            raise stripe_unavailable()
        try:
            with httpx.Client(
                base_url=self.BASE_URL, auth=(self.settings.stripe_secret_key, ""), timeout=15, transport=self.transport
            ) as client:
                res = client.request(method, path, **kw)
        except httpx.HTTPError:
            raise stripe_unavailable()
        if res.status_code >= 400:  # never echo Stripe's body: it may contain request details
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "stripe_error")
        return res.json()

    def start_session(self, user: User) -> tuple[str, str]:
        """Returns (session_id, hosted verification url)."""
        data = self._request(
            "POST",
            "/identity/verification_sessions",
            data={
                "type": "document",
                "metadata[user_id]": str(user.id),
                "return_url": f"{self.settings.public_base_url.rstrip('/')}/verify?done=1",
                "options[document][require_matching_selfie]": "false",
            },
        )
        return data["id"], data["url"]

    def retrieve(self, session_id: str) -> dict:
        return self._request("GET", f"/identity/verification_sessions/{session_id}", params={"expand[]": "verified_outputs"})

    def parse_event(self, raw_body: bytes, header: str | None) -> dict:
        """Verifies `Stripe-Signature: t=...,v1=...` (HMAC-SHA256 of `{t}.{body}`) and returns the event."""
        secret = self.settings.stripe_webhook_secret
        if not secret or not header:
            raise bad_signature()
        parts = [p.split("=", 1) for p in header.split(",") if "=" in p]
        stamps = [v for k, v in parts if k.strip() == "t"]
        sigs = [v for k, v in parts if k.strip() == "v1"]
        try:
            t = int(stamps[0])
        except (IndexError, ValueError):
            raise bad_signature()
        if abs(time.time() - t) > self.TOLERANCE_SECONDS:
            raise bad_signature()
        expected = hmac.new(secret.encode(), f"{t}.".encode() + raw_body, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected.encode(), s.strip().encode()) for s in sigs):  # bytes: no TypeError on non-ASCII
            raise bad_signature()
        try:
            return json.loads(raw_body)
        except ValueError:
            raise bad_signature()


class IdentityService:
    def __init__(self, db: Session, settings: Settings, stripe: StripeIdentity | None = None):
        self.db, self.settings = db, settings
        self.stripe = stripe or StripeIdentity(settings)

    def status(self, user: User) -> dict:
        return {
            "status": user.verification,
            "provider": user.verification_provider,
            "is_adult": user.is_adult,
            "verified_at": user.verified_at,
            "demo_available": self.settings.demo_mode,
            "stripe_available": self.stripe.available,
            "stripe_test_mode": self.stripe.available and self.stripe.test_mode,
        }

    def verify_demo(self, user: User) -> User:
        if user.verification != Verification.unverified:  # idempotent; never downgrades verified_live
            return user
        user.verification, user.is_adult = Verification.verified_demo, True
        user.verification_provider, user.verified_at = "demo", now()
        self.db.add(ConsentEvent(user_id=user.id, kind="verification_demo", scope={"confirm_adult": True}))
        self.db.commit()
        return user

    def start_stripe(self, user: User) -> str:
        session_id, url = self.stripe.start_session(user)
        user.verification_session_id = session_id
        if user.verification != Verification.verified_live:
            user.verification_provider = "stripe"
        self.db.commit()
        return url

    def handle_webhook(self, raw_body: bytes, signature: str | None) -> None:
        event = self.stripe.parse_event(raw_body, signature)
        if not isinstance(event, dict) or event.get("type") != VERIFIED_EVENT:
            return
        data = event.get("data")
        obj = data.get("object") if isinstance(data, dict) else None
        session_id = obj.get("id") if isinstance(obj, dict) else None
        if not isinstance(session_id, str) or not session_id:
            return
        # Correlate by the session id WE stored; metadata.user_id is never trusted on its own.
        user = self.db.scalar(select(User).where(User.verification_session_id == session_id))
        if user is None or user.verification == Verification.verified_live:
            return
        session = self.stripe.retrieve(session_id)  # source of truth, not the webhook payload
        if session.get("status") != "verified":
            return
        user.verification, user.verification_provider = Verification.verified_live, "stripe"
        user.is_adult = self.is_adult((session.get("verified_outputs") or {}).get("dob"))
        user.verified_at = now()
        self.db.commit()

    @staticmethod
    def is_adult(dob: dict | None, today: date | None = None) -> bool:
        try:
            born = date(int(dob["year"]), int(dob["month"]), int(dob["day"]))
        except (TypeError, KeyError, ValueError):
            return False
        today = today or date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return age >= 18
