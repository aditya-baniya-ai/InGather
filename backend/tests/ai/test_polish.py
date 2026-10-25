from types import SimpleNamespace

from app.ai import icebreaker
from app.ai.venues import strip_coordinates
from app.config import Settings


def test_venue_reasons_never_show_coordinates():
    assert strip_coordinates("Fair travel from the 39.96,-75.15 midpoint, quiet") == "Fair travel from the middle of your group, quiet"
    assert strip_coordinates("Near (39.96, -75.16) and quiet") == "Near the middle of your group and quiet"
    assert strip_coordinates("Open 7am-7pm, covers 6-7pm.") == "Open 7am-7pm, covers 6-7pm."


def test_icebreaker_falls_back_without_key():
    assert icebreaker.write_icebreaker(Settings(model_api_key=""), "Coffee", "cafe", ["coffee"], "Template?") == "Template?"


def test_icebreaker_uses_muse_answer_and_rejects_bad_ones(monkeypatch):
    def client(text):
        out = [SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text=text)])]
        return SimpleNamespace(ai_live=True, responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output=out)))
    s = Settings(model_api_key="k")
    monkeypatch.setattr(icebreaker, "MuseClient", lambda _s: client("Which Philly coffee spot should we try next?"))
    assert icebreaker.write_icebreaker(s, "Coffee", "cafe", ["coffee"], "T?") == "Which Philly coffee spot should we try next?"
    monkeypatch.setattr(icebreaker, "MuseClient", lambda _s: client("Not a question"))
    assert icebreaker.write_icebreaker(s, "Coffee", "cafe", ["coffee"], "T?") == "T?"


def test_icebreaker_uses_interests_most_of_the_group_shares():
    from app.services.proposals import common_interests
    groups = [["tech", "food", "coffee"], ["tech", "food"], ["tech", "museums"], ["coffee", "city exploring"]]
    assert common_interests(groups) == ["tech", "coffee", "food"]
    assert common_interests([["a"], ["b"]]) == []
