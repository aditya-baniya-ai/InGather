"""Scene agent covers: specific brief -> Muse Image, shared per scene, private, and shown in the feed."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.ai.muse import GeneratedImage
from app.ai.scenes import SceneAgent
from app.demo.austin import AustinSeeder
from app.models import Proposal
from app.services import covers
from tests.ai.fakes import FakeMuse, answer


class Painter(FakeMuse):
    """Fake Muse: scripted scene briefs, and an image call that records its prompt."""

    def __init__(self, *turns):
        super().__init__(*turns)
        self.prompts = []

    def generate_image(self, prompt):
        self.prompts.append(prompt)
        return GeneratedImage(b"RIFF-fake-webp", "webp")


@pytest.fixture
def media(tmp_path, settings, monkeypatch):
    monkeypatch.setattr(settings, "media_dir", str(tmp_path))
    return tmp_path


def test_brief_is_specific_and_private(settings):
    fake = Painter([answer({"scene": "Dawn on the Barton Creek Greenbelt: three hikers with headlamps on a pale limestone trail, mist over the creek, trekking poles."})])
    agent = SceneAgent(fake, settings)
    brief = agent.brief("Sunrise hike on the Greenbelt", "other", "Austin", "morning", ["hiking", "dogs"])
    assert "Greenbelt" in brief and "limestone" in brief
    sent = str(fake.responses.requests[0]["input"])
    assert "Sunrise hike on the Greenbelt" in sent and "morning" in sent and "tools" not in fake.responses.requests[0]
    agent.render(brief)
    assert fake.prompts[0].startswith(brief) and "no text" in fake.prompts[0]  # realism rules appended


def test_brief_falls_back_to_the_category_scene(settings):
    class Down:
        class responses:
            @staticmethod
            def create(**_):
                raise RuntimeError("down")

    brief = SceneAgent(Down(), settings).brief("Taco spot hunt", "event", "Austin", "evening", [])
    assert "Taco spot hunt" in brief and "Austin" in brief


def test_groups_get_their_own_cover_and_same_scenes_share_one(db, users, settings, media):
    AustinSeeder(db, settings, n=60, groups=6).run()
    groups = [p for p in db.scalars(select(Proposal)) if p.open_to_requests]
    a, b = groups[0], groups[1]
    b.activity_title = a.activity_title  # same title, city and (forced) part of day -> same scene
    b.start_at = a.start_at
    db.commit()
    fake = Painter([answer({"scene": "A specific scene for the first group, with lots of concrete detail to draw."})])
    url_a = covers.make_cover(db, settings, a, fake)
    url_b = covers.make_cover(db, settings, b, fake)
    assert url_a == url_b and url_a.startswith("/media/scene-") and (Path(media) / Path(url_a).name).exists()
    assert len(fake.prompts) == 1  # the second group reused the image
    names = [m.user.display_name for m in a.members]
    assert not any(n.split()[0] in fake.prompts[0] or n.split()[0] in str(fake.responses.requests) for n in names)  # no names sent


def test_feed_shows_covers_and_queues_missing_ones(db, users, settings, austin_small):
    from app.services.feed import Feed

    items = Feed(db, settings).items(users["alice"])
    assert all(i.cover_url is None for i in items) and len(covers.missing(items)) == min(4, len(items))
    target = db.get(Proposal, items[0].proposal_id)
    target.cover_image_url = "/media/scene-abc.webp"
    db.commit()
    again = Feed(db, settings).items(users["alice"])
    assert next(i for i in again if i.proposal_id == target.id).cover_url == "/media/scene-abc.webp"
    assert target.id not in covers.missing(again)


@pytest.fixture
def austin_small(db, users, settings):
    return AustinSeeder(db, settings, n=60, groups=6).run()


def test_background_job_is_a_no_op_without_muse(settings, monkeypatch):
    monkeypatch.setattr(type(settings), "ai_live", property(lambda self: False))
    covers.cover_in_background([SimpleNamespace()])  # returns before touching anything
