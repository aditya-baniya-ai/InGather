import hashlib
import hmac
import json
import time
from datetime import date

import httpx
import pytest

from app.api import verification
from app.config import Settings, get_settings
from app.models import ConsentEvent, User, Verification
from app.services.identity import IdentityService, StripeIdentity

SESSION = "vs_test_123"
KEYS = dict(stripe_secret_key="sk_test_abc", stripe_webhook_secret="whsec_test", public_base_url="http://app.test")


@pytest.fixture
def app(app):
    app.include_router(verification.router)
    return app


@pytest.fixture
def stripe(app, monkeypatch):
    """Stripe configured + a mocked Stripe API. `stripe.dob` controls verified_outputs.dob."""

    class Fake:
        dob = {"day": 1, "month": 1, "year": 1990}
        requests: list[httpx.Request] = []

        def handler(self, req: httpx.Request) -> httpx.Response:
            self.requests.append(req)
            if req.method == "POST":
                return httpx.Response(200, json={"id": SESSION, "url": "https://verify.stripe.com/start/x"})
            return httpx.Response(200, json={"id": SESSION, "status": "verified", "verified_outputs": {"dob": self.dob}})

    fake = Fake()
    fake.requests = []
    app.dependency_overrides[get_settings] = lambda: Settings(model_api_key="", **KEYS)
    monkeypatch.setattr(StripeIdentity, "transport", httpx.MockTransport(fake.handler))
    return fake


@pytest.fixture
def bob(client, db):
    res = client.post("/api/auth/register", json={"email": "bob@x.example", "password": "bob-password", "display_name": "Bob"})
    assert res.status_code == 200
    return db.query(User).filter_by(email="bob@x.example").one()


def signed(payload: dict, secret: str = "whsec_test", t: int | None = None) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    t = t or int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"Stripe-Signature": f"t={t},v1={sig}", "Content-Type": "application/json"}


def verified_event(session_id: str = SESSION) -> dict:
    return {"type": "identity.verification_session.verified", "data": {"object": {"id": session_id, "metadata": {}}}}


def post_webhook(client, payload, **kw):
    body, headers = signed(payload, **kw)
    return client.post("/api/webhooks/stripe", content=body, headers=headers)


def test_demo_verify_enables_discovery(db, as_user, bob):
    api = as_user(bob)
    assert api.get("/api/verification").json() == {
        "status": "unverified", "provider": None, "is_adult": False, "verified_at": None,
        "demo_available": True, "stripe_available": False, "stripe_test_mode": False,
    }
    assert api.post("/api/verification/demo", {"confirm_adult": False}).status_code == 422
    res = api.post("/api/verification/demo", {"confirm_adult": True})
    assert res.status_code == 200 and res.json()["verification"] == "verified_demo" and res.json()["can_discover"] is True
    db.refresh(bob)
    assert bob.is_adult and bob.verification_provider == "demo" and bob.verified_at
    status = api.get("/api/verification").json()
    assert status["status"] == "verified_demo" and status["provider"] == "demo" and status["is_adult"]
    api.post("/api/verification/demo", {"confirm_adult": True})  # idempotent
    assert db.query(ConsentEvent).filter_by(user_id=bob.id, kind="verification_demo").count() == 1


def test_demo_verify_404_outside_demo_mode(app, db, as_user, bob):
    app.dependency_overrides[get_settings] = lambda: Settings(demo_mode=False, model_api_key="")
    assert as_user(bob).post("/api/verification/demo", {"confirm_adult": True}).status_code == 404
    db.refresh(bob)
    assert bob.verification == Verification.unverified and not bob.is_adult


def test_demo_never_downgrades_live(db, as_user, bob):
    bob.verification, bob.is_adult = Verification.verified_live, True
    db.commit()
    assert as_user(bob).post("/api/verification/demo", {"confirm_adult": True}).json()["verification"] == "verified_live"


def test_patch_me_cannot_set_verification_fields(db, as_user, bob):
    as_user(bob).patch("/api/me", {"verification": "verified_live", "is_adult": True, "verification_provider": "stripe",
                                   "verification_session_id": SESSION, "verified_at": "2026-01-01T00:00:00Z"})
    db.refresh(bob)
    assert bob.verification == Verification.unverified and not bob.is_adult
    assert bob.verification_provider is None and bob.verification_session_id is None and bob.verified_at is None


def test_stripe_start_unavailable_without_key(as_user, bob):
    res = as_user(bob).post("/api/verification/stripe/start")
    assert res.status_code == 503 and res.json() == {"detail": "stripe_unavailable"}


def test_stripe_start_creates_session(db, as_user, bob, stripe):
    res = as_user(bob).post("/api/verification/stripe/start")
    assert res.status_code == 200 and res.json() == {"url": "https://verify.stripe.com/start/x"}
    req = stripe.requests[0]
    assert req.url.path == "/v1/identity/verification_sessions" and req.headers["authorization"].startswith("Basic ")
    form = dict(httpx.QueryParams(req.content.decode()))
    assert form["type"] == "document" and form["metadata[user_id]"] == str(bob.id)
    assert form["return_url"] == "http://app.test/verify?done=1"
    db.refresh(bob)
    assert bob.verification_session_id == SESSION and bob.verification_provider == "stripe"
    assert bob.verification == Verification.unverified  # only the signed webhook can verify
    status = as_user(bob).get("/api/verification").json()
    assert status["stripe_available"] and status["stripe_test_mode"]


def test_webhook_rejects_bad_signatures(client, db, as_user, bob, stripe):
    as_user(bob).post("/api/verification/stripe/start")
    assert post_webhook(client, verified_event(), secret="whsec_wrong").status_code == 400
    assert post_webhook(client, verified_event(), t=int(time.time()) - 301).status_code == 400
    assert client.post("/api/webhooks/stripe", content=json.dumps(verified_event())).status_code == 400
    db.refresh(bob)
    assert bob.verification == Verification.unverified


@pytest.mark.parametrize("year, adult", [(1990, True), (date.today().year - 17, False)])
def test_webhook_verifies_live_with_adulthood_from_dob(client, db, as_user, bob, stripe, year, adult):
    stripe.dob = {"day": 1, "month": 1, "year": year}
    as_user(bob).post("/api/verification/stripe/start")
    assert post_webhook(client, verified_event()).status_code == 200
    db.refresh(bob)
    assert bob.verification == Verification.verified_live and bob.is_adult is adult and bob.verified_at
    retrieve = stripe.requests[-1]
    assert retrieve.method == "GET" and retrieve.url.path == f"/v1/identity/verification_sessions/{SESSION}"
    assert retrieve.url.params["expand[]"] == "verified_outputs"
    assert as_user(bob).get("/api/me").json()["can_discover"] is adult


def test_webhook_replay_is_idempotent(client, db, as_user, bob, stripe):
    as_user(bob).post("/api/verification/stripe/start")
    body, headers = signed(verified_event())
    assert client.post("/api/webhooks/stripe", content=body, headers=headers).status_code == 200
    db.refresh(bob)
    first, calls = bob.verified_at, len(stripe.requests)
    assert client.post("/api/webhooks/stripe", content=body, headers=headers).status_code == 200
    db.refresh(bob)
    assert bob.verification == Verification.verified_live and bob.verified_at == first and len(stripe.requests) == calls


def test_webhook_unknown_session_and_other_events_are_noops(client, db, users, as_user, bob, stripe):
    as_user(bob).post("/api/verification/stripe/start")
    event = verified_event("vs_someone_else")
    event["data"]["object"]["metadata"] = {"user_id": str(bob.id)}  # metadata alone is never trusted
    assert post_webhook(client, event).status_code == 200
    assert post_webhook(client, {"type": "identity.verification_session.requires_input", "data": {"object": {"id": SESSION}}}).status_code == 200
    db.expire_all()
    assert db.query(User).filter(User.verification == Verification.verified_live).count() == 0
    assert len(stripe.requests) == 1  # only the start call; no retrieve


def test_is_adult_boundaries():
    today = date(2026, 10, 24)
    assert IdentityService.is_adult({"day": 24, "month": 10, "year": 2008}, today)
    assert not IdentityService.is_adult({"day": 25, "month": 10, "year": 2008}, today)
    assert not IdentityService.is_adult(None, today) and not IdentityService.is_adult({"year": 1990}, today)


@pytest.mark.parametrize("value", [1, "true", "yes", 1.0, None])
def test_demo_verify_requires_json_true(db, as_user, bob, value):
    assert as_user(bob).post("/api/verification/demo", {"confirm_adult": value}).status_code == 422
    db.refresh(bob)
    assert bob.verification == Verification.unverified


def test_webhook_non_ascii_signature_is_400(client, stripe):
    body = json.dumps(verified_event()).encode()
    header = f"t={int(time.time())},v1=\xe9".encode("latin-1")
    res = client.post("/api/webhooks/stripe", content=body, headers=[(b"stripe-signature", header)])
    assert res.status_code == 400


@pytest.mark.parametrize("payload", [[1, 2], {"type": "identity.verification_session.verified", "data": [1]},
                                     {"type": "identity.verification_session.verified", "data": {"object": "vs_x"}},
                                     {"type": "identity.verification_session.verified", "data": {"object": {"id": 5}}}])
def test_webhook_malformed_signed_events_are_noops(client, db, as_user, bob, stripe, payload):
    as_user(bob).post("/api/verification/stripe/start")
    assert post_webhook(client, payload).status_code == 200
    db.refresh(bob)
    assert bob.verification == Verification.unverified and len(stripe.requests) == 1
