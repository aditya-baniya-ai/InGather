"""Supabase Auth sign-in: real people only; the demo accounts and the 1,000 Austin residents never touch Supabase."""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.config import get_settings
from app.models import User
from app.services import supabase_auth

URL = "https://abcd1234.supabase.co"
KEY = ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def supabase(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "supabase_url", URL)
    monkeypatch.setattr(s, "supabase_anon_key", "anon-public-key")
    monkeypatch.setattr(s, "supabase_jwt_secret", "legacy-secret-legacy-secret-legacy-secret")
    monkeypatch.setattr(supabase_auth, "_jwks", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda t: SimpleNamespace(key=KEY.public_key())))
    return s


def token(sub="sb-user-1", email="Riley@Example.com", key=KEY, alg="ES256", **over):
    claims = {"sub": sub, "email": email, "aud": "authenticated", "iss": f"{URL}/auth/v1", "role": "authenticated",
              "exp": int(time.time()) + 600, "user_metadata": {"display_name": "Riley Park"}, **over}
    return jwt.encode(claims, key, algorithm=alg)


def test_config_is_public_and_off_without_settings(client, supabase, monkeypatch):
    body = client.get("/api/auth/config").json()
    assert body == {"supabase_url": URL, "supabase_anon_key": "anon-public-key", "demo_mode": True}
    monkeypatch.setattr(supabase, "supabase_anon_key", "")
    assert client.get("/api/auth/config").json()["supabase_url"] is None
    assert client.post("/api/auth/supabase", json={"access_token": token()}).status_code == 404


def test_first_sign_in_creates_a_profile_then_reuses_it(client, db, supabase):
    r = client.post("/api/auth/supabase", json={"access_token": token()})
    assert r.status_code == 200, r.text
    me = r.json()["user"]
    assert me["display_name"] == "Riley Park" and me["verification"] == "unverified" and me["can_discover"] is False
    again = client.post("/api/auth/supabase", json={"access_token": token(email="riley@example.com")}).json()["user"]
    assert again["id"] == me["id"]
    user = db.query(User).filter(User.supabase_id == "sb-user-1").one()
    assert user.email == "riley@example.com" and not user.is_demo
    # The local password login can't be used for a Supabase-only account
    assert client.post("/api/auth/login", json={"email": "riley@example.com", "password": "!supabase"}).status_code == 401
    assert client.get("/api/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_legacy_hs256_projects_work(client, supabase):
    t = token(sub="sb-legacy", email="legacy@example.com", key=supabase.supabase_jwt_secret, alg="HS256")
    assert client.post("/api/auth/supabase", json={"access_token": t}).status_code == 200


@pytest.mark.parametrize("bad", [
    {"aud": "anon"}, {"iss": "https://evil.supabase.co/auth/v1"}, {"exp": int(time.time()) - 10},
    {"role": "anon"}, {"is_anonymous": True}, {"email": ""},
])
def test_rejects_tokens_that_are_not_a_signed_in_user_of_this_project(client, supabase, bad):
    assert client.post("/api/auth/supabase", json={"access_token": token(**bad)}).status_code == 401


def test_rejects_forged_and_unsigned_tokens(client, supabase):
    other = ec.generate_private_key(ec.SECP256R1())
    assert client.post("/api/auth/supabase", json={"access_token": token(key=other)}).status_code == 401
    assert client.post("/api/auth/supabase", json={"access_token": token(key="wrong-secret-wrong-secret-wrong", alg="HS256")}).status_code == 401
    unsigned = jwt.encode({"sub": "x", "email": "x@example.com", "aud": "authenticated", "iss": f"{URL}/auth/v1",
                           "role": "authenticated", "exp": int(time.time()) + 60}, None, algorithm="none")
    assert client.post("/api/auth/supabase", json={"access_token": unsigned}).status_code == 401


def test_never_takes_over_existing_or_demo_accounts(client, users, supabase):
    t = token(sub="sb-attacker", email="alice@ingather.example")
    assert client.post("/api/auth/supabase", json={"access_token": t}).json()["detail"] == "email_taken"


def test_local_registration_is_closed_when_supabase_is_on(client, supabase):
    r = client.post("/api/auth/register", json={"email": "new@example.com", "password": "long-password-1", "display_name": "New"})
    assert r.status_code == 409 and r.json()["detail"] == "use_supabase"
