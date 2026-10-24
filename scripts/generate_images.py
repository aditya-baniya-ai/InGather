"""Generate the static activity/city photo library with Muse Image.

Run once (costs one Muse Image call per missing file):  cd backend && uv run python ../scripts/generate_images.py
Writes frontend/public/images/<name>.jpg (resized with macOS `sips`); existing files are skipped.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ai.muse import MuseClient  # noqa: E402
from app.config import get_settings  # noqa: E402

STYLE = "Editorial lifestyle photograph, natural light, warm and inviting, shallow depth of field, no text, no logos, no recognizable faces."
SUBJECTS = {
    "conference": "A modern conference venue foyer at golden hour, attendees chatting in small groups with lanyards, coffee cups on high tables.",
    "travel": "A traveler's view of a charming city street at dusk, string lights, cafés and people strolling.",
    "hackathon": "A lively university hackathon at night: laptops, stickers, snacks and small teams collaborating at long tables.",
    "study": "A bright university library study space with books, laptops and a small study group at a wooden table.",
    "coffee": "A cozy specialty coffee shop with latte art on a table by a sunny window, friends chatting in the background.",
    "event": "An outdoor evening music event with festoon lights and a small group of friends enjoying the atmosphere.",
    "other": "A small group of friends walking through a sunny city park, seen from behind, autumn trees.",
    "city-philadelphia": "Philadelphia at golden hour: historic brick rowhouses and the skyline, a lively street with cafés.",
    "city-austin": "Austin, Texas at sunset: the skyline over Lady Bird Lake with the UT Austin tower in the distance.",
}


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "frontend/public/images"
    out.mkdir(parents=True, exist_ok=True)
    client = MuseClient(get_settings())
    if not client.ai_live:
        sys.exit("MODEL_API_KEY is not set.")
    for name, subject in SUBJECTS.items():
        target = out / f"{name}.jpg"
        if target.exists():
            continue
        image = client.generate_image(f"{subject} {STYLE}")
        raw = out / f"{name}.{image.fmt}"
        raw.write_bytes(image.data)
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "72", "-Z", "1200", str(raw), "--out", str(target)], check=True, capture_output=True)
        raw.unlink()
        print(f"{name}: {target.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
