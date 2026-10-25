import io

from PIL import Image
"""Optional "about you" fields (opt-in, members only) and personal avatars (generated or uploaded)."""
import pytest

from app.demo.austin import AustinSeeder
from app.models import User
from app.services.feed import Feed
from app.services.profile import Avatars
from tests.helpers import approve
from tests.test_chats import confirmed
from tests.test_proposals import accept, flow  # noqa: F401

agent = pytest.mark.usefixtures("fake_agent")
ABOUT = {"gender": "woman", "age_range": "25-34", "work": "Software engineer at Dell", "education": "UT Austin, CS"}
ALL_ON = {"show_gender": True, "show_age": True, "show_background": True}


@pytest.fixture(autouse=True)
def media(tmp_path, monkeypatch):
    monkeypatch.setattr(Avatars, "media", staticmethod(lambda name="": tmp_path / "avatars" / name))
    return tmp_path / "avatars"


def image(fmt: str, size=(900, 600), **save) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 80, 120)).save(buf, fmt, **save)
    return buf.getvalue()


def sofia_in(api, pid):
    return next(m for m in api.get(f"/api/proposals/{pid}").json()["members"] if m["display_name"] == "Sofia")


@agent
def test_details_only_for_members_and_only_when_switched_on(users, as_user, flow, db, settings):
    alice, pid = flow
    sofia = as_user(users["sofia"])
    assert sofia.patch("/api/me", ABOUT).status_code == 200
    approve(alice, pid, users["sofia"], users["jordan"])
    assert sofia_in(alice, pid)["details"] == []  # filled in but every switch is off
    assert sofia.patch("/api/me", ALL_ON).json()["show_age"] is True
    assert sofia_in(alice, pid)["details"] == ["Woman", "25–34", "Software engineer at Dell", "UT Austin, CS"]
    invitee = as_user(users["jordan"]).get(f"/api/proposals/{pid}").json()  # invited, not yet accepted
    assert invitee["viewer_role"] == "invitee" and "Dell" not in str(invitee)
    assert as_user(users["eve"]).get(f"/api/proposals/{pid}").status_code == 404
    accept(as_user, users, pid, "sofia", "jordan")
    assert sofia_in(as_user(users["jordan"]), pid)["details"][0] == "Woman"
    sofia.patch("/api/me", {"show_gender": False, "show_background": False})
    assert sofia_in(alice, pid)["details"] == ["25–34"]


def test_feed_never_shows_details(users, db, settings):
    AustinSeeder(db, settings, n=40, groups=4).run()
    for person in db.query(User):
        for k, v in {**ABOUT, **ALL_ON}.items():
            setattr(person, k, v)
    db.commit()
    items = Feed(db, settings).items(users["eve"])
    assert items and "Dell" not in str([i.model_dump() for i in items])


@agent
def test_chat_people_carry_switched_on_details(users, as_user, flow):
    as_user(users["sofia"]).patch("/api/me", {**ABOUT, "show_background": True})
    alice, _ = confirmed(users, as_user, flow)
    people = [p for c in alice.get("/api/chats").json() for p in c["people"] if p["display_name"] == "Sofia"]
    assert people and all(p["details"] == ["Software engineer at Dell", "UT Austin, CS"] for p in people)


def test_me_update_validation_and_owner_fields(users, as_user, db):
    users["alice"].avatar_url = None
    db.commit()
    me = as_user(users["alice"])
    assert me.get("/api/me").json()["avatar_url"].startswith("/api/avatars/")  # lazily generated
    for bad in ({"gender": "robot"}, {"age_range": "30"}, {"work": "x" * 121}, {"gender_self": "x" * 41}, {"show_age": "yes"}):
        assert me.patch("/api/me", bad).status_code == 422, bad
    out = me.patch("/api/me", {"gender": "self_describe", "gender_self": " Agender ", "show_gender": True}).json()
    assert out["gender_self"] == "Agender" and out["show_gender"] and not out["show_age"]
    out = me.patch("/api/me", {"gender": "", "work": ""}).json()
    assert out["gender"] is None and out["gender_self"] is None and out["work"] is None


def test_generated_avatar_follows_gender_but_photos_stay(client, as_user, db):
    reg = client.post("/api/auth/register", json={"email": "new@x.example", "password": "longpassword", "display_name": "New"}).json()
    assert reg["user"]["avatar_kind"] == "generated"
    me = as_user(db.query(User).filter_by(email="new@x.example").one())
    url = me.get("/api/me").json()["avatar_url"]
    assert url == reg["user"]["avatar_url"] and url.startswith("/api/avatars/") and "?g=" not in url
    seed = url.split("/")[-1].split(".")[0]
    assert me.patch("/api/me", {"gender": "man"}).json()["avatar_url"] == f"/api/avatars/{seed}.svg?g=man"
    shuffled = me.post("/api/me/avatar/shuffle").json()
    assert shuffled["avatar_kind"] == "generated" and seed not in shuffled["avatar_url"] and shuffled["avatar_url"].endswith("?g=man")
    photo = client.post("/api/me/avatar", headers=me.headers, files={"photo": ("a.png", image("PNG"), "text/plain")})
    assert photo.status_code == 200 and photo.json()["avatar_url"].startswith("/media/avatars/") and photo.json()["avatar_kind"] == "photo"
    assert me.patch("/api/me", {"gender": "woman"}).json()["avatar_url"] == photo.json()["avatar_url"]
    back = me.delete("/api/me/avatar").json()
    assert back["avatar_kind"] == "generated" and back["avatar_url"].endswith("?g=woman")


def test_upload_rejects_non_images_and_oversize(users, as_user, client, media):
    me = as_user(users["alice"])
    post = lambda data, ctype="image/png": client.post("/api/me/avatar", headers=me.headers, files={"photo": ("x.png", data, ctype)})
    assert post(b"<svg onload=alert(1)>").status_code == 415
    assert post(b"GIF89a" + b"0" * 10, "image/gif").status_code == 415
    assert post(b"\xff\xd8\xff" + b"0" * (3 * 1024 * 1024)).status_code == 413
    assert post(b"RIFF\0\0\0\0WEBPVP8 ").status_code == 415  # header only, not a real image
    assert post(image("WEBP")).status_code == 200
    assert [p.suffix for p in media.iterdir()] == [".webp"]


def test_uploaded_photos_lose_their_gps_metadata(users, as_user, client, media):
    me = as_user(users["alice"])
    exif = Image.Exif()
    exif[0x8825] = {2: (30.0, 16.0, 0.0), 4: (97.0, 44.0, 0.0)}  # GPSInfo: Austin
    exif[0x010F] = "PhoneMaker"
    res = client.post("/api/me/avatar", headers=me.headers, files={"photo": ("p.jpg", image("JPEG", exif=exif.tobytes()), "image/jpeg")})
    assert res.status_code == 200
    saved = next(media.iterdir()).read_bytes()
    with Image.open(io.BytesIO(saved)) as out:
        assert out.format == "WEBP" and not out.getexif() and "exif" not in out.info and max(out.size) <= 512
    assert client.post("/api/me/avatar", files={"photo": ("x.png", b"\x89PNG\r\n\x1a\n")}).status_code == 401


def test_avatar_endpoint_serves_svg_and_rejects_bad_seeds(client):
    res = client.get("/api/avatars/abcdef0123456789.svg?g=woman")
    assert res.status_code == 200 and res.headers["content-type"] == "image/svg+xml" and "public" in res.headers["cache-control"]
    for g in ("woman", "man", "any"):  # beards only ever come from the "man" pool
        svgs = [client.get(f"/api/avatars/seed{i:06d}.svg?g={g}").text for i in range(40)]
        assert any('d="M40 78Q43 100' in s for s in svgs) == (g == "man")
    for bad in ("short", "UPPERCASE123", "a" * 33, "..%2f..%2fetc"):
        assert client.get(f"/api/avatars/{bad}.svg").status_code == 404
