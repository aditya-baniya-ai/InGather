"""Icebreaker agent: Muse Spark writes the Gather Room's opening question once a group confirms.

Privacy: the model sees only the activity, the venue type and the interests the group shares — no names,
plans, schedules or locations. Any failure falls back to the deterministic template already on the proposal.
"""

import logging

from app.ai.intake import answer_text
from app.ai.muse import MuseClient
from app.config import Settings

log = logging.getLogger(__name__)

PROMPT = (
    "Write ONE warm, natural icebreaker question (max 20 words) for a small group of adults meeting for the first "
    "time. Activity: {activity}. Place: a {venue}. Interests they all share: {interests}. Make it specific to those "
    "interests, easy for anyone to answer, and not personal or sensitive. Reply with the question only."
)


def write_icebreaker(settings: Settings, activity: str, venue_category: str, shared: list[str], fallback: str) -> str:
    client = MuseClient(settings)
    if not client.ai_live:
        return fallback
    try:
        resp = client.responses.create(
            model=settings.meta_model,
            reasoning={"effort": "minimal"},
            input=PROMPT.format(activity=activity[:80], venue=venue_category.replace("_", " "), interests=", ".join(shared[:5]) or "meeting new people"),
        )
        text = (answer_text(resp) or "").strip().strip('"')
        return text[:280] if 5 < len(text) <= 280 and text.endswith("?") else fallback
    except Exception as exc:
        log.warning("icebreaker failed: %s", type(exc).__name__)
        return fallback
