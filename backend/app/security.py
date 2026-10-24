"""Authentication. The acting user is ALWAYS derived from the verified token, never from request bodies."""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)


class Passwords:
    @staticmethod
    def hash(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify(password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed.encode())


class Tokens:
    ALGO = "HS256"

    @classmethod
    def issue(cls, user_id: uuid.UUID) -> str:
        s = get_settings()
        exp = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_ttl_minutes)
        return jwt.encode({"sub": str(user_id), "exp": exp, "aud": "ingather"}, s.jwt_secret, algorithm=cls.ALGO)

    @classmethod
    def decode(cls, token: str) -> uuid.UUID:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[cls.ALGO], audience="ingather")
        return uuid.UUID(payload["sub"])


def unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in", headers={"WWW-Authenticate": "Bearer"})


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise unauthorized()
    try:
        user_id = Tokens.decode(creds.credentials)
    except (jwt.PyJWTError, ValueError, KeyError):
        raise unauthorized()
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized()
    return user


def not_found() -> HTTPException:
    """Uniform privacy-preserving denial: never reveals whether the resource exists."""
    return HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
