"""Optional "about you" fields and personal avatars (generated illustrations or an uploaded photo).

The about-you fields are self-reported and owner-controlled: never used to match or rank, never sent to an AI model,
and only turned into `details` for people who already see the accepted roster, field by field, when switched on.
"""

import io
import re
import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps

from app.models import User

GENDERS = {"woman": "Woman", "man": "Man", "non_binary": "Non-binary", "self_describe": None, "prefer_not_to_say": None}
AGE_RANGES = {"18-24": "18–24", "25-34": "25–34", "35-44": "35–44", "45-54": "45–54", "55+": "55+"}
SEED = re.compile(r"^[a-z0-9]{8,32}$")
GENERATED = re.compile(r"^/api/avatars/([a-z0-9]{8,32})\.svg(?:\?g=\w+)?$")
PHOTO_TYPES = {b"\xff\xd8\xff": "jpg", b"\x89PNG\r\n\x1a\n": "png"}
MAX_PHOTO = 3 * 1024 * 1024
MAX_PIXELS = 40_000_000  # refuse decompression bombs
PHOTO_SIDE = 512


def details(user: User) -> list[str]:
    """Human-readable chips for the fields this person chose to show. Callers decide whether the viewer may see them."""
    out = []
    if user.show_gender and user.gender:
        label = GENDERS.get(user.gender) or (user.gender_self if user.gender == "self_describe" else None)
        out += [label] if label else []
    if user.show_age and user.age_range in AGE_RANGES:
        out.append(AGE_RANGES[user.age_range])
    if user.show_background:
        out += [v for v in (user.work, user.education) if v]
    return out


class Avatars:
    """Generated portraits live at /api/avatars/<seed>.svg?g=<gender>: no user data, just a random seed."""

    @staticmethod
    def url(seed: str, gender: str | None) -> str:
        return f"/api/avatars/{seed}.svg" + (f"?g={gender}" if gender else "")

    @staticmethod
    def seed(user: User) -> str | None:
        m = GENERATED.match(user.avatar_url or "")
        return m.group(1) if m else None

    @classmethod
    def generate(cls, user: User, seed: str | None = None) -> None:
        cls.drop_photo(user)
        user.avatar_url = cls.url(seed or secrets.token_hex(8), user.gender)

    @classmethod
    def ensure(cls, user: User) -> bool:
        """Give a person without any avatar a generated one; returns whether anything changed."""
        if user.avatar_url:
            return False
        cls.generate(user)
        return True

    @classmethod
    def restyle(cls, user: User) -> None:
        """After a gender change, keep the same generated face seed but redraw it from the matching style pool."""
        if seed := cls.seed(user):
            user.avatar_url = cls.url(seed, user.gender)

    @staticmethod
    def media(name: str = "") -> Path:
        from app.config import get_settings
        return Path(get_settings().media_dir) / "avatars" / name

    @classmethod
    def drop_photo(cls, user: User) -> None:
        url = user.avatar_url or ""
        if url.startswith("/media/avatars/"):
            cls.media(Path(url).name).unlink(missing_ok=True)

    @staticmethod
    def clean(data: bytes) -> bytes:
        """Re-encode the photo so no metadata (EXIF GPS location, camera serials) ever reaches other people."""
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.width * im.height > MAX_PIXELS:
                    raise ValueError("too many pixels")
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((PHOTO_SIDE, PHOTO_SIDE))
                out = io.BytesIO()
                im.save(out, "WEBP", quality=85)  # a fresh file: no EXIF, no XMP, no ICC comments
                return out.getvalue()
        except (OSError, ValueError, Image.DecompressionBombError):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported_image")

    @classmethod
    async def upload(cls, user: User, photo: UploadFile) -> None:
        data = await photo.read(MAX_PHOTO + 1)
        if len(data) > MAX_PHOTO:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "photo_too_large")
        ext = next((e for magic, e in PHOTO_TYPES.items() if data.startswith(magic)), None)
        if ext is None and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            ext = "webp"
        if ext is None:  # decided by magic bytes only; the client's content-type and filename are ignored
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported_image")
        cls.media().mkdir(parents=True, exist_ok=True)
        name = f"{secrets.token_hex(16)}.webp"
        cls.media(name).write_bytes(cls.clean(data))
        cls.drop_photo(user)
        user.avatar_url = f"/media/avatars/{name}"
