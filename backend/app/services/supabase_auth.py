"""Verify Supabase Auth access tokens. Real people sign up and sign in with Supabase; InGather then issues its own
session token for a local profile linked by Supabase user id. The demo accounts never involve Supabase.

Tokens are checked against the project's published signing keys (JWKS, ES256/RS256), or the legacy shared HS256
secret if SUPABASE_JWT_SECRET is set. Audience must be "authenticated" and the issuer this project's /auth/v1.
"""

from functools import lru_cache

import jwt

from app.config import Settings


class InvalidSupabaseToken(Exception):
    pass


@lru_cache
def _jwks(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=3600)


def verify(token: str, settings: Settings) -> dict:
    url = settings.supabase_url.rstrip("/")
    options = {"require": ["exp", "sub", "aud", "iss"]}
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise InvalidSupabaseToken("hs256_without_secret")
            key, algorithms = settings.supabase_jwt_secret, ["HS256"]
        else:
            key, algorithms = _jwks(url).get_signing_key_from_jwt(token).key, ["ES256", "RS256"]
        claims = jwt.decode(token, key, algorithms=algorithms, audience="authenticated", issuer=f"{url}/auth/v1", options=options)
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidSupabaseToken(type(exc).__name__) from exc
    if claims.get("is_anonymous") or claims.get("role") != "authenticated" or not claims.get("email"):
        raise InvalidSupabaseToken("not_a_signed_in_user")
    return claims
