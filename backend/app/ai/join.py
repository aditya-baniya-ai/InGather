"""Muse Spark around joining a group (never for deciding who fits: that's the matcher).

- intro_draft: before asking to join, writes a short, friendly intro from the requester's own profile.
- welcome_note: after the host accepts, writes a warm note telling the new member what the group has in common.

Privacy: the model sees the requester's own bio and interests (only for their own draft), the group's activity, the
kind of place, the day and part of day, and shared interests. Never other people's names, profiles or schedules.
Without a key or on any failure, both fall back to plain templates.
"""

import logging

from app.ai.intake import answer_text
from app.ai.muse import MuseClient
from app.config import Settings

log = logging.getLogger(__name__)

INTRO = (
    "Write a short, friendly message (max 2 sentences, 220 characters) that a person sends when asking to join a small "
    "public meetup with people they haven't met. Speak as them, in first person, casual and genuine, no clichés, no "
    "emoji, no contact details. Mention why the activity appeals to them using only these facts.\n"
    "Their profile: {bio}\nTheir interests: {interests}\nThe meetup: {activity}, at a {venue}, {when}.\n"
    "Interests they share with the group: {shared}. Reply with the message only."
)
WELCOME = (
    "Write a warm welcome note (max 2 sentences, 220 characters) for someone whose request to join a small public "
    "meetup was just accepted. Address them by first name ({first}). Say what the group has in common and one thing "
    "to look forward to. No emoji, no promises about safety, no other people's names.\n"
    "The meetup: {activity}, at a {venue}, {when}. Shared interests: {shared}. Reply with the note only."
)


def _ask(settings: Settings, prompt: str) -> str | None:
    client = MuseClient(settings)
    if not client.ai_live:
        return None
    try:
        resp = client.responses.create(model=settings.meta_model, reasoning={"effort": "minimal"}, input=prompt)
        text = " ".join((answer_text(resp) or "").strip().strip('"').split())
        return text if 10 <= len(text) <= 400 and "@" not in text and "http" not in text else None
    except Exception as exc:
        log.warning("join text failed: %s", type(exc).__name__)
        return None


def _list(items: list[str]) -> str:
    return ", ".join(items[:4]) or "meeting new people"


def intro_draft(settings: Settings, bio: str | None, interests: list[str], activity: str, venue: str, when: str, shared: list[str]) -> tuple[str, bool]:
    """(message, written_by_muse)."""
    text = _ask(settings, INTRO.format(bio=(bio or "")[:280], interests=_list(interests), activity=activity[:80],
                                        venue=venue.replace("_", " "), when=when, shared=_list(shared)))
    if text:
        return text[:400], True
    hook = f" I'm into {_list(shared)} too." if shared else ""
    return f"Hi! {activity} sounds great.{hook} Would love to join if there's room.", False


def welcome_note(settings: Settings, first: str, activity: str, venue: str, when: str, shared: list[str]) -> str:
    text = _ask(settings, WELCOME.format(first=first[:30], activity=activity[:80], venue=venue.replace("_", " "), when=when, shared=_list(shared)))
    if text:
        return text[:400]
    common = f" You all share {_list(shared)}." if shared else ""
    return f"Welcome, {first}! You're in for {activity}, {when}.{common}"
