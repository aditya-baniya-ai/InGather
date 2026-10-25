"""Scene agent: a dedicated Muse Spark step that turns a group's activity into one specific, detailed photo brief,
which Muse Image then renders as that group's cover. "Taco spot hunt" and "Sunrise hike on the Greenbelt" get their
own pictures instead of one stock photo per category.

Privacy: the agent sees only the public activity title, the kind of activity, the city, the part of day and broad
interest tags. Never names, plan text or locations of people.
"""

import json
import logging
import re

from app.ai.imagery import REALISM, SCENES
from app.ai.intake import answer_text, obj, parse_json

log = logging.getLogger(__name__)
PRIVATE = re.compile(r"\b(apartment|bedroom|living room|dorm|hotel room|someone's home|their home|house party|couch|sofa)\b", re.I)

SCHEMA = obj({
    "scene": {"type": "string", "description": "One paragraph, 40-90 words: the exact photo to take"},
})

INSTRUCTIONS = (
    "You are the InGather scene agent. You write the brief for ONE realistic photo that shows what this small group "
    "meetup will look like, so people recognise it at a glance in a feed. Be specific and concrete: the real, "
    "well-known public setting the title points to in that city (for example a named trail, park, market, street or "
    "kind of venue), the light at that part of the day, what a few people are doing, and 3-5 telling objects or details "
    "(food, gear, signage shapes, textures, weather). Match the activity exactly: a taco hunt shows tacos and a taqueria "
    "or food truck, a sunrise hike shows a trail at dawn, a study group shows notes and books. People are seen from "
    "behind or small in frame, never identifiable. No text, words, logos or brand names in the image. No famous people. "
    "The setting is ALWAYS a public place where the group meets; never a private home, apartment, bedroom, dorm room or "
    "hotel room, and never a messy or abandoned interior. If the title and the kind of activity disagree, show the "
    "title's activity at that kind of public place (e.g. a photo walk starting from a café shows people with cameras "
    "on a lively street outside a café). "
    "Write only the scene, as plain description, no camera jargon."
)


def fallback_brief(title: str, activity: str, city: str, part_of_day: str) -> str:
    base = SCENES.get(activity, SCENES["other"]).format(city=city or "a US city")
    return f"A scene for '{title}' in {city}, {part_of_day} light: {base}"


class SceneAgent:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings  # MuseClient (or a fake with .responses and .generate_image)

    def brief(self, title: str, activity: str, city: str, part_of_day: str, interests: list[str]) -> str:
        """A specific photo brief from Muse Spark; a category template if the call fails."""
        try:
            resp = self.client.responses.create(
                model=self.settings.meta_model, instructions=INSTRUCTIONS,
                input=[{"role": "user", "content": json.dumps({
                    "activity_title": title[:120], "kind_of_activity": activity, "city": city[:80],
                    "part_of_day": part_of_day, "interests": [i for i in interests[:4] if len(i) < 30],
                })}],
                text={"format": {"type": "json_schema", "name": "scene_brief", "schema": SCHEMA, "strict": True}},
            )
            text = answer_text(resp)
            scene = str(parse_json(text).get("scene") or "").strip() if text else ""
        except Exception as exc:
            log.warning("scene brief failed: %s", type(exc).__name__)
            scene = ""
        if len(scene) < 30 or PRIVATE.search(scene):  # never render someone's home, whatever the model wrote
            return fallback_brief(title, activity, city, part_of_day)
        return scene[:900]

    def render(self, brief: str):
        """Muse Image, with the shared realism rules (phone photo, natural light, no text, no posed faces)."""
        return self.client.generate_image(f"{brief} {REALISM}")
