from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.schemas import AuthConfigOut, DemoAccountOut, DemoLoginIn, LoginIn, MeOut, MeUpdate, RegisterIn, SupabaseIn, TokenOut
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


@router.get("/auth/config", response_model=AuthConfigOut)
def auth_config(s: Settings = Depends(get_settings)):
    on = s.supabase_auth
    return AuthConfigOut(supabase_url=s.supabase_url.rstrip("/") if on else None, supabase_anon_key=s.supabase_anon_key if on else None,
                         demo_mode=s.demo_mode)


@router.post("/auth/supabase", response_model=TokenOut)
def supabase_session(body: SupabaseIn, db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    """Exchange a Supabase Auth access token for an InGather session, creating the profile on first sign-in."""
    from app.services.supabase_auth import InvalidSupabaseToken, verify

    if not s.supabase_auth:
        raise not_found()
    try:
        claims = verify(body.access_token, s)
    except InvalidSupabaseToken:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")
    limiter.hit("login", claims["sub"])
    email = str(claims["email"]).lower()
    user = db.scalar(select(User).where(User.supabase_id == claims["sub"]))
    if user is None:
        if by_email(db, email):
            # Never attach a Supabase login to an existing profile (a demo account, a local account, another Supabase
            # user): unless the project enforces email confirmation, that would let anyone claim someone else's email.
            raise HTTPException(status.HTTP_409_CONFLICT, "email_taken")
        meta = claims.get("user_metadata") or {}
        name = (body.display_name or meta.get("display_name") or meta.get("full_name") or email.split("@")[0]).strip()[:60]
        user = User(email=email, password_hash="!supabase", display_name=name or "New member", supabase_id=claims["sub"])
        db.add(user)
        db.commit()
    return token_out(user, db, s)


@router.post("/auth/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    if s.supabase_auth:  # real people register through Supabase Auth when it's configured
        raise HTTPException(status.HTTP_409_CONFLICT, "use_supabase")
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
    # The named demo cast only; the 1,000 synthetic Austin residents (app/demo) are people to meet, not logins to pick.
    from app.demo.austin import DOMAIN

    return db.scalars(select(User).where(User.is_demo.is_(True), User.email.not_like(f"%{DOMAIN}")).order_by(User.created_at)).all()


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
