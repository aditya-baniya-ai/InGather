"""Interest space: maps the free-text interests people type in InGather onto the Meetup.com topic vocabulary the
matcher was trained on, and gives each known interest a learned embedding (PPMI + SVD over 1.7M real Meetup
members' topic lists, see backend/ml/train.py). Similar interests ("machine learning", "data science") end up
close together even when the words differ.

Pure numpy and shared by training and serving, so features are computed the same way in both.
"""

import re
from dataclasses import dataclass, field

import numpy as np

# InGather interest words -> Meetup topic tags. Only needed where simple spelling variants don't already match.
ALIASES: dict[str, tuple[str, ...]] = {
    "ai": ("machine-learning", "robotics"),
    "artificial intelligence": ("machine-learning", "robotics"),
    "ml": ("machine-learning",),
    "data science": ("machine-learning", "data-analytics", "big-data"),
    "data": ("data-analytics", "big-data"),
    "tech": ("newtech", "technology"),
    "technology": ("newtech", "technology"),
    "coding": ("programming", "software-development"),
    "software": ("software-development", "programming"),
    "web dev": ("web-development",),
    "hackathon": ("hacking", "hackerspaces"),
    "hackathons": ("hacking", "hackerspaces"),
    "startup": ("startup-businesses", "entrepreneurship"),
    "startups": ("startup-businesses", "entrepreneurship"),
    "entrepreneurs": ("entrepreneurship",),
    "food": ("food-lovers", "foodie", "diningout"),
    "foodie": ("foodie", "food-lovers"),
    "dining": ("diningout",),
    "dinner": ("diningout",),
    "restaurants": ("diningout", "exploring-new-restaurants"),
    "tacos": ("foodie", "ethnic-food"),
    "brunch": ("brunchclub",),
    "beer": ("craft-beer", "beer"),
    "museums": ("museum",),
    "galleries": ("art-museums-galleries",),
    "art": ("art",),
    "photography": ("photo",),
    "photos": ("photo",),
    "film": ("film", "indiefilm"),
    "films": ("film", "indiefilm"),
    "live music": ("livemusic",),
    "concerts": ("livemusic",),
    "books": ("bookclub", "book-discussion"),
    "reading": ("bookclub", "book-discussion"),
    "book club": ("bookclub",),
    "board games": ("boardgames",),
    "games": ("boardgames", "videogame"),
    "video games": ("videogame",),
    "gaming": ("videogame", "boardgames"),
    "walking": ("walkers", "walking-and-hiking"),
    "walks": ("walkers",),
    "city exploring": ("exploring", "sightseeing", "hiking-and-city-walks"),
    "exploring": ("exploring",),
    "sightseeing": ("sightseeing",),
    "outdoors": ("outdoors", "outdoor-recreation"),
    "biking": ("bike", "cycling"),
    "cycling": ("cycling", "bike"),
    "climbing": ("rockclimbing",),
    "gym": ("fitness",),
    "workout": ("fitness",),
    "friendship": ("make-new-friends", "friends"),
    "friends": ("make-new-friends", "friends"),
    "meeting people": ("meeting-new-people",),
    "new people": ("meeting-new-people",),
    "networking": ("professional-networking", "business-networking"),
    "career": ("career-development", "career-network"),
    "design": ("graphicdesign", "webdesign", "user-experience"),
    "ux": ("user-experience", "ux"),
    "product": ("productdesign",),
    "languages": ("language", "language-exchange"),
    "language exchange": ("language-exchange",),
    "studying": ("education",),
    "study": ("education",),
    "writing": ("writing", "writers"),
    "volunteering": ("volunteering", "volunteerism"),
    "podcasts": ("podcasting",),
    "standup": ("comedy",),
    "improv": ("improv-comedy",),
    # Austin demo interests outside the Meetup top-5000 topics (none of these keys is itself a vocabulary topic).
    "paddleboarding": ("kayaking", "outdoors"),
    "food trucks": ("foodie", "food-lovers"),
    "vinyl": ("livemusic", "music"),
    "thrifting": ("bargainhunters", "vintage"),
    "crafts": ("arts-crafts", "diy"),
    "sci-fi": ("science-fiction", "scifi"),
}
_SPACE = re.compile(r"[\s_]+")


def normalize(term: str) -> str:
    return _SPACE.sub(" ", str(term).strip().lower())[:40]


def spellings(term: str) -> list[str]:
    """Meetup tag spellings a typed interest could match: as typed, hyphenated, joined, and singular/plural."""
    t = normalize(term)
    out = list(ALIASES.get(t, ()))
    for base in (t, t[:-1] if t.endswith("s") and len(t) > 3 else t + "s"):
        out += [base.replace(" ", "-"), base.replace(" ", "")]
    return list(dict.fromkeys(out))


@dataclass
class InterestSpace:
    """Topic vocabulary + unit-length embeddings. `vectors(terms)` returns one vector per known term."""

    tags: list[str]
    matrix: np.ndarray  # (len(tags), dim) float32, rows unit length
    index: dict[str, int] = field(init=False)

    def __post_init__(self):
        self.index = {t: i for i, t in enumerate(self.tags)}

    def rows(self, term: str) -> list[int]:
        return [self.index[s] for s in spellings(term) if s in self.index]

    def key(self, term: str) -> str:
        """Canonical key for exact matching, so "Museums" and "museum" count as the same interest."""
        rows = self.rows(term)
        return self.tags[rows[0]] if rows else normalize(term)

    def vector(self, term: str) -> np.ndarray | None:
        rows = self.rows(term)
        if not rows:
            return None
        v = self.matrix[rows].mean(0)
        n = float(np.linalg.norm(v))
        return v / n if n else None

    def profile(self, terms) -> "Profile":
        keys, vecs = [], []
        for t in terms:
            if not normalize(t):
                continue
            k = self.key(t)
            if k in keys:
                continue
            keys.append(k)
            v = self.vector(t)
            vecs.append(v)
        return Profile(keys, vecs)


@dataclass
class Profile:
    """One side of a pair: canonical interest keys plus their vectors (None for interests outside the vocabulary)."""

    keys: list[str]
    vecs: list[np.ndarray | None]

    @property
    def known(self) -> np.ndarray:
        rows = [v for v in self.vecs if v is not None]
        return np.stack(rows) if rows else np.zeros((0, 0), np.float32)

    def merged(self, other: "Profile") -> "Profile":
        keys, vecs = list(self.keys), list(self.vecs)
        for k, v in zip(other.keys, other.vecs):
            if k not in keys:
                keys.append(k)
                vecs.append(v)
        return Profile(keys, vecs)
