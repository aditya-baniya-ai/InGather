"""Prompts for realistic Muse Image photos: one place for plan covers and the static photo library.

Only activity type, city and broad interests go in — never names, goal text or other personal data.
"""

SCENES = {
    "conference": "attendees with lanyards talking in small groups in the lobby of a convention center in {city}, coffee cups, badges, a registration sign out of focus",
    "travel": "an ordinary street in a well-known neighborhood of {city}, pedestrians with backpacks and a paper map, local storefronts",
    "hackathon": "university students hacking overnight at long folding tables in a campus building in {city}, laptops with stickers, energy drinks, pizza boxes, whiteboards with diagrams",
    "study": "students studying together at a big wooden table in a public library in {city}, open textbooks, highlighters, laptops, coffee cups, tall shelves behind",
    "coffee": "a busy neighborhood coffee shop in {city}, a barista at the counter, a few people talking at small tables, cups and pastries",
    "event": "a crowd at an outdoor evening community event in {city}, food stalls and string lights, people chatting in small groups",
    "other": "a few friends walking and talking on a sidewalk in {city}, seen from behind, everyday street life",
}

REALISM = (
    "Candid documentary photo taken on a phone, eye level, available light, slightly imperfect framing, "
    "real textures and everyday clutter, natural colors, no dramatic lighting, no bokeh fireworks, no glossy CGI or "
    "illustration look, no posed models, faces small or turned away, no text, no logos, wide landscape composition."
)


def photo_prompt(activity: str, city: str, interests: list[str] | None = None) -> str:
    scene = SCENES.get(activity, SCENES["other"]).format(city=city[:60] or "a US city")
    tags = ", ".join(i for i in (interests or [])[:3] if i.replace(" ", "").isalnum())
    return f"{scene}{f', with small details hinting at {tags}' if tags else ''}. Real place details typical of {city[:60]}. {REALISM}"
