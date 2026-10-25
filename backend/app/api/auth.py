from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.schemas import DemoAccountOut, DemoLoginIn, LoginIn, MeOut, MeUpdate, RegisterIn, TokenOut
from app.security import Passwords, Tokens, current_user, not_found
from app.services.policy import Policy
from app.services.ratelimit import limiter

router = APIRouter(prefix="/api", tags=["auth"])


def me_out(user: User, db: Session, s: Settings) -> MeOut:
    return MeOut.build(user, Policy(db, s).can_discover(user))


def token_out(user: User, db: Session, s: Settings) -> TokenOut:
    return TokenOut(access_token=Tokens.issue(user.id), user=me_out(user, db, s))


def by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


@router.post("/auth/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    limiter.hit("login", body.email.lower())
    if by_email(db, body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "email_taken")
    user = User(email=body.email.lower(), password_hash=Passwords.hash(body.password), display_name=body.display_name)
    db.add(user)
    db.commit()
    return token_out(user, db, s)


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    limiter.hit("login", body.email.lower())
    user = by_email(db, body.email)
    if user is None or not Passwords.verify(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")
    return token_out(user, db, s)


@router.get("/auth/demo-accounts", response_model=list[DemoAccountOut])
def demo_accounts(db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    if not s.demo_mode:
        raise not_found()
    return db.scalars(select(User).where(User.is_demo.is_(True)).order_by(User.created_at)).all()


@router.post("/auth/demo-login", response_model=TokenOut)
def demo_login(body: DemoLoginIn, db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    user = by_email(db, body.email) if s.demo_mode else None
    if user is None or not user.is_demo:
        raise not_found()
    return token_out(user, db, s)


@router.get("/me", response_model=MeOut)
def get_me(user: User = Depends(current_user), db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    return me_out(user, db, s)


@router.patch("/me", response_model=MeOut)
def update_me(
    body: MeUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings),
):
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    area = data.pop("home_area", None)
    for field, value in data.items():
        setattr(user, field, value)
    if area is not None:
        from app.services.geo import geocode_area
        area = area.strip()
        if area != (user.home_area or ""):
            user.home_area = area or None
            point = geocode_area(area, s.venue_search_enabled) if area else None
            user.home_lat, user.home_lng = point if point else (None, None)
    db.commit()
    return me_out(user, db, s)
