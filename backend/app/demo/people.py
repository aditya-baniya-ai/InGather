"""Synthetic Austin residents for the demo: realistic-looking but entirely fictional people.

Everything is generated from a fixed seed, so every machine gets the same 1,000 people. Interests come from a few
coherent "lifestyles" (an outdoorsy runner tends to also like tacos and dogs), which gives the matcher real
structure to find, the way real people's interests cluster. Free time follows weekly patterns ("weekday evenings
after 6", "Saturday mornings") over the coming week, and the "about" text says the same thing in plain words.
"""

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from app.services.clock import Interval, as_utc

TZ = "America/Chicago"
CITY = "Austin"

FIRST = """Aaliyah Aaron Abigail Adrian Aisha Alejandro Alex Alexis Ali Alicia Amanda Amara Amir Ana Andre Andrea Andrew
Angela Anjali Anthony Ari Arjun Ashley Austin Ava Ben Bianca Brandon Brianna Caleb Camila Carlos Carmen Cassidy Chloe
Chris Christian Claire Cole Connor Daisy Daniel Danielle Darius David Deja Derek Destiny Devin Diana Diego Dominic
Elena Eli Elijah Elise Emeka Emily Emma Eric Esther Ethan Eva Fatima Felix Gabriel Gabriela Grace Hannah Hector Hiro
Imani Isaac Isabel Isabella Ivan Jack Jacob Jade Jamal Jasmine Jason Javier Jenna Jessica Joaquin Joel Jonah Jordan
Jose Joshua Julia Julian Justin Kai Kayla Kenji Kevin Kiara Kim Kyle Laila Lauren Leah Leo Liam Lily Lucas Lucia Luis
Luke Maddie Malik Marcus Maria Mariana Mason Matt Maya Megan Mei Mia Michael Miguel Mina Mohammed Morgan Nadia Naomi
Nate Nia Nicole Nina Noah Nora Olivia Omar Paige Pablo Priya Quinn Rachel Rafael Rahul Raquel Ravi Rebecca Ricardo
Riley Rohan Rosa Ryan Sam Samantha Sara Sebastian Shreya Simone Sofia Sophie Stephanie Tanvi Tariq Taylor Tessa
Thomas Tiana Tyler Valeria Vanessa Victor Vikram Wei Will Xavier Yasmin Yusuf Zach Zara Zoe""".split()

LAST = """Abbott Acosta Adeyemi Aguilar Ahmed Alvarez Anderson Bailey Banerjee Barnes Bell Bennett Brooks Bui Burke Campbell
Cardenas Carter Castillo Castro Chang Chavez Chen Cho Clark Coleman Collins Cooper Cruz Daniels Davis Delgado Diaz
Dixon Dominguez Edwards Ellis Espinoza Evans Fernandez Fischer Flores Foster Garcia Gomez Gonzalez Gordon Graham
Green Guerrero Gupta Gutierrez Hall Harris Hayes Henderson Hernandez Herrera Hill Hoang Hughes Ibarra Iyer Jackson
James Jenkins Jimenez Johnson Jones Kapoor Kelly Khan Kim Lam Le Lee Lewis Lin Liu Lopez Luna Martin Martinez Medina
Mendoza Meyer Miller Mitchell Molina Montgomery Moore Morales Moreno Murphy Nakamura Nash Nguyen Novak Okafor Okoye
Olson Ortiz Owens Park Patel Pena Perez Perry Peterson Pham Phillips Price Ramirez Ramos Rao Reed Reyes Reynolds
Rivera Roberts Robinson Rodriguez Rojas Romero Ross Ruiz Russell Salazar Sanchez Sandoval Santos Schmidt Scott Shah
Shapiro Silva Simmons Singh Smith Sosa Stewart Sullivan Tanaka Taylor Thomas Thompson Torres Tran Turner Valdez Vargas
Vasquez Vega Walker Wang Ward Washington Watson White Williams Wilson Wong Wright Wu Yang Young Zhang Zimmerman""".split()

# Real Austin neighborhoods with coarse (~1 km) centers. Home areas stay private; they only feed group midpoints.
NEIGHBORHOODS = [
    ("Hyde Park", 30.31, -97.73), ("East Austin", 30.26, -97.72), ("South Congress", 30.25, -97.75),
    ("Mueller", 30.30, -97.70), ("Zilker", 30.26, -97.77), ("Travis Heights", 30.25, -97.74),
    ("North Loop", 30.32, -97.72), ("Clarksville", 30.28, -97.76), ("Bouldin Creek", 30.25, -97.76),
    ("Cherrywood", 30.29, -97.71), ("Crestview", 30.34, -97.73), ("Allandale", 30.34, -97.75),
    ("Downtown", 30.27, -97.74), ("Rainey Street", 30.26, -97.74), ("The Domain", 30.40, -97.72),
    ("Windsor Park", 30.31, -97.69), ("Holly", 30.25, -97.73), ("West Campus", 30.29, -97.75),
    ("Riverside", 30.24, -97.73), ("North Burnet", 30.39, -97.72), ("Brentwood", 30.33, -97.73),
    ("Barton Hills", 30.25, -97.78), ("East Cesar Chavez", 30.26, -97.73), ("St. Johns", 30.34, -97.70),
]

# Public meeting anchors that people sometimes mention for a plan (the matcher's "same event" signal).
EVENTS = {
    "hackathon": ["UT Austin campus"],
    "conference": ["Austin Convention Center"],
    "study": ["Austin Central Library", "Perry-Castañeda Library, UT Austin"],
}


@dataclass(frozen=True)
class Lifestyle:
    key: str
    interests: tuple[str, ...]
    activities: tuple[str, ...]  # plan types this kind of person tends to make
    jobs: tuple[str, ...]
    likes: tuple[str, ...]  # "about" fragments
    wants: tuple[tuple[str, str], ...]  # (what they're looking for this week, plan title)


LIFESTYLES = [
    Lifestyle("tech", ("tech", "startups", "ai", "programming", "coffee", "board games", "design", "data science", "hackathons"),
              ("coffee", "hackathon", "conference", "event"),
              ("software engineer", "product manager", "data scientist", "UX designer", "founder of a small startup",
               "machine learning engineer", "QA engineer", "solutions architect", "frontend developer"),
              ("talking shop over cold brew", "side projects that never quite ship", "demo nights", "a good mechanical keyboard"),
              (("a few people to grab coffee and talk startups", "Coffee and startup talk"), ("a small crew for a hack night", "Hack night crew"),
               ("people to swap side-project ideas with", "Side-project swap"), ("a couple of folks to check out a tech meetup with", "Tech meetup buddies"))),
    Lifestyle("outdoors", ("hiking", "running", "biking", "outdoors", "kayaking", "climbing", "paddleboarding", "dogs", "camping", "swimming"),
              ("event", "other", "coffee"),
              ("park ranger", "physical therapist", "civil engineer", "environmental scientist", "nurse", "landscape architect",
               "bike mechanic", "teacher"),
              ("early runs on the Lady Bird Lake trail", "Barton Springs on a hot day", "weekend trips to the Greenbelt",
               "my dog, who sets the pace"),
              (("a small group for a sunrise hike", "Sunrise hike on the Greenbelt"), ("people to paddle Lady Bird Lake with", "Paddling Lady Bird Lake"),
               ("a running buddy or two", "Easy run around the lake"), ("a group to try a new climbing gym", "Climbing gym session"))),
    Lifestyle("music", ("live music", "jazz", "concerts", "karaoke", "dancing", "craft beer", "vinyl", "trivia", "comedy"),
              ("event", "other"),
              ("sound engineer", "bartender", "music teacher", "event producer", "graphic designer", "barista",
               "radio producer", "paralegal"),
              ("catching shows on Red River", "digging through record bins", "two-stepping badly but happily", "open mic nights"),
              (("a few people to catch a live show with", "Live music night"), ("a group for trivia night", "Trivia night team"),
               ("people to try a new music venue with", "New music venue"), ("a karaoke crew that doesn't take itself too seriously", "Karaoke night"))),
    Lifestyle("food", ("food", "tacos", "bbq", "brunch", "cooking", "coffee", "wine", "food trucks", "baking"),
              ("coffee", "event", "other"),
              ("line cook", "food photographer", "dietitian", "restaurant manager", "pastry chef", "marketing manager",
               "account executive", "nurse practitioner"),
              ("hunting down the best breakfast tacos", "food truck crawls", "a slow Sunday brunch", "trying every bakery in town"),
              (("people to try a new taco spot with", "Taco spot hunt"), ("a small group for a food truck crawl", "Food truck crawl"),
               ("a brunch crew for the weekend", "Weekend brunch crew"), ("a couple of people to cook and swap recipes with", "Recipe swap and coffee"))),
    Lifestyle("arts", ("art", "museums", "photography", "film", "theater", "writing", "design", "poetry", "crafts"),
              ("event", "travel", "coffee"),
              ("illustrator", "museum educator", "architect", "photographer", "copywriter", "art teacher", "film editor",
               "interior designer"),
              ("gallery openings on the East Side", "film nights at the Paramount", "sketching in coffee shops", "zine fairs"),
              (("a few people for a gallery walk", "East Side gallery walk"), ("a group to see an indie film", "Indie film night"),
               ("people to go on a photo walk with", "Photo walk"), ("a couple of folks for a museum afternoon", "Museum afternoon"))),
    Lifestyle("books", ("books", "book club", "languages", "history", "podcasts", "philosophy", "coffee", "writing", "sci-fi"),
              ("study", "coffee", "other"),
              ("librarian", "high school teacher", "PhD student", "technical writer", "translator", "editor", "historian",
               "policy analyst"),
              ("a long afternoon at the library", "used bookstores", "language exchanges", "a podcast I won't stop recommending"),
              (("a small book club that actually meets", "Small book club"), ("a language exchange partner or two", "Language exchange"),
               ("people to study with at the library", "Library study session"), ("a coffee chat about whatever we're reading", "Books and coffee"))),
    Lifestyle("fitness", ("yoga", "fitness", "running", "meditation", "pilates", "soccer", "volleyball", "tennis", "basketball"),
              ("other", "event", "coffee"),
              ("personal trainer", "physical therapist", "yoga instructor", "sales manager", "nurse", "accountant",
               "sports coach", "dental hygienist"),
              ("sunrise yoga at Zilker", "pickup soccer on weekends", "a long run before work", "trying every studio class pass"),
              (("people for a pickup soccer game", "Pickup soccer"), ("a yoga-then-coffee group", "Yoga, then coffee"),
               ("a running group for weekday mornings", "Morning run club"), ("a few people to try a new fitness class with", "Trying a new fitness class"))),
    Lifestyle("games", ("board games", "video games", "anime", "chess", "dnd", "trivia", "sci-fi", "coffee"),
              ("event", "coffee", "other"),
              ("game developer", "IT support specialist", "pharmacist", "electrical engineer", "student", "data analyst",
               "animator", "logistics coordinator"),
              ("board game cafés", "a long-running D&D campaign", "chess in the park", "anime marathons"),
              (("a couple of people for a board game night", "Board game night"), ("players for a one-shot D&D session", "One-shot D&D session"),
               ("a chess partner at a café", "Café chess"), ("a group to check out a game café", "Game café meetup"))),
    Lifestyle("community", ("volunteering", "sustainability", "gardening", "dogs", "community", "cooking", "outdoors"),
              ("event", "other", "coffee"),
              ("nonprofit coordinator", "social worker", "urban planner", "city employee", "high school counselor",
               "public health researcher", "community organizer", "veterinary technician"),
              ("Saturday shifts at a community garden", "fostering dogs", "neighborhood cleanups", "farmers markets"),
              (("a few people to volunteer with this weekend", "Volunteering this weekend"), ("a group for a farmers market morning", "Farmers market morning"),
               ("people to join a park cleanup", "Park cleanup"), ("a dog-friendly coffee meetup", "Dog-friendly coffee"))),
    Lifestyle("student", ("studying", "coffee", "hackathons", "football", "languages", "tech", "video games", "food"),
              ("study", "hackathon", "coffee"),
              ("UT Austin student", "UT Austin grad student", "ACC student", "UT Austin research assistant", "teaching assistant"),
              ("late nights at the PCL", "game days in Austin", "cheap tacos near campus", "hackathon weekends"),
              (("a study group for the week", "Study group this week"), ("teammates for a hackathon", "Hackathon teammates"),
               ("people to grab coffee between classes", "Coffee between classes"), ("a group to explore Austin beyond campus", "Exploring Austin beyond campus"))),
]
BY_KEY = {lf.key: lf for lf in LIFESTYLES}
LIFESTYLE_WEIGHTS = {"tech": 14, "outdoors": 12, "music": 11, "food": 13, "arts": 9, "books": 8, "fitness": 10, "games": 7,
                     "community": 6, "student": 10}

# Weekly free-time patterns: (label for the about text, days of week 0=Mon, start, end).
PATTERNS = [
    ("weekday evenings after 6", range(0, 5), time(18), time(21, 30)),
    ("weekday mornings before work", range(0, 5), time(7), time(9)),
    ("weekday lunchtimes", range(0, 5), time(12), time(13, 30)),
    ("Saturday mornings", (5,), time(8, 30), time(12)),
    ("weekend afternoons", (5, 6), time(13), time(17)),
    ("Sunday mornings", (6,), time(9), time(12)),
    ("Friday and Saturday evenings", (4, 5), time(18, 30), time(22, 30)),
    ("Tuesday and Thursday evenings", (1, 3), time(18), time(21)),
]

DISPLAY = {"ai": "AI", "dnd": "D&D", "bbq": "BBQ", "ux": "UX"}
INTENTS = (("friends", 55), ("activity", 30), ("networking", 15))


@dataclass
class Person:
    key: str  # stable id, e.g. "atx-0042"
    first: str
    last: str
    job: str
    area: tuple[str, float, float]
    lifestyle: str
    interests: list[str]
    bio: str
    activity: str
    intent: str
    title: str
    goal: str
    preview: str
    public_location: str | None
    patterns: list[int] = field(default_factory=list)
    group_min: int = 3
    group_max: int = 4

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}"

    @property
    def email(self) -> str:
        return f"{self.first.lower()}.{self.last.lower()}.{self.key[-4:]}@atx.ingather.example"


def _pick(rng: random.Random, weights: dict[str, int]) -> str:
    keys = list(weights)
    return rng.choices(keys, [weights[k] for k in keys])[0]


def _join(items: list[str]) -> str:
    items = [DISPLAY.get(i, i) for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _about(rng: random.Random, job: str, area: str, lf: Lifestyle, interests: list[str], when: list[str], want: str) -> str:
    """Short, natural "about" text: who they are, what they're into, when they're free and what they want."""
    article = "a" if job.startswith("UT") else "an" if job[0].lower() in "aeiou" or job.startswith("ACC") else "a"
    opener = rng.choice([
        f"{article.capitalize()} {job} living in {area}.",
        f"{job[0].upper() + job[1:]} based in {area}.",
        f"{article.capitalize()} {job}, new-ish to {area}.",
        f"{article.capitalize()} {job} who loves {area}.",
    ])
    likes = rng.choice([
        f"Into {_join(interests[:3])}.",
        f"Big on {_join(interests[:2])}, and always up for {_join(interests[2:3]) if len(interests) > 2 else 'something new'}.",
        f"Spends free time on {_join(interests[:3])}.",
        f"Favorite way to spend a Saturday: {rng.choice(lf.likes)}. Also into {_join(interests[:2])}.",
    ])
    free = rng.choice([f"Free {_join(when)} this week", f"This week I'm free {_join(when)}", f"Usually free {_join(when)}"])
    ask = rng.choice(["looking for", "hoping to find", "would love to meet"])
    text = f"{opener} {likes} {free}, {ask} {want}."
    return text if len(text) <= 280 else f"{opener} {likes} {free}."[:280]


def generate(n: int = 1000, seed: int = 2026) -> list[Person]:
    rng = random.Random(seed)
    people, used = [], set()
    for i in range(n):
        while True:
            first, last = rng.choice(FIRST), rng.choice(LAST)
            if (first, last) not in used:
                used.add((first, last))
                break
        lf = BY_KEY[_pick(rng, LIFESTYLE_WEIGHTS)]
        other = BY_KEY[_pick(rng, {k: w for k, w in LIFESTYLE_WEIGHTS.items() if k != lf.key})]
        interests = rng.sample(lf.interests, rng.randint(3, 4))
        interests += [x for x in rng.sample(other.interests, rng.randint(1, 2)) if x not in interests]
        area = rng.choice(NEIGHBORHOODS)
        job = rng.choice(lf.jobs)
        activity = rng.choice(lf.activities)
        intent = rng.choices([k for k, _ in INTENTS], [w for _, w in INTENTS])[0]
        if lf.key == "tech" and rng.random() < 0.35:
            intent = "networking"
        patterns = sorted(rng.sample(range(len(PATTERNS)), rng.choice((1, 2, 2, 3))))
        if lf.key == "student" and 2 not in patterns:  # students skew to lunch breaks and evenings
            patterns = sorted({*patterns[:1], 2})
        want, title = rng.choice(lf.wants)
        when = [PATTERNS[p][0] for p in patterns]
        bio = _about(rng, job, area[0], lf, interests, when, want)
        goal = f"I'm in {area[0]} and free {_join(when)}. I'd love {want}, especially if you're into {_join(interests[:2])}."
        preview = f"{job[0].upper() + job[1:]} in Austin, into {_join(interests[:3])}."[:200]
        location = rng.choice(EVENTS[activity]) if activity in EVENTS and rng.random() < 0.7 else None
        size = rng.choice(((3, 4), (3, 4), (3, 3), (2, 3), (4, 4)))
        people.append(Person(
            key=f"atx-{i:04d}", first=first, last=last, job=job, area=area, lifestyle=lf.key, interests=interests,
            bio=bio, activity=activity, intent=intent, title=title[:120], goal=goal[:2000], preview=preview,
            public_location=location, patterns=patterns, group_min=size[0], group_max=size[1],
        ))
    return people


def week_windows(person: Person, today: date, days: int = 7) -> list[Interval]:
    """The person's free windows for the coming week, as UTC intervals (local wall-clock times in Austin)."""
    from zoneinfo import ZoneInfo

    zone, out = ZoneInfo(TZ), []
    for d in range(days):
        day = today + timedelta(days=d)
        for p in person.patterns:
            _, weekdays, start, end = PATTERNS[p]
            if day.weekday() in weekdays:
                out.append((as_utc(datetime.combine(day, start, zone)), as_utc(datetime.combine(day, end, zone))))
    return out
