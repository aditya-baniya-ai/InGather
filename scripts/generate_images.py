"""Generate the static photo library with Muse Image, using the same realistic prompts as plan covers.

Run (one Muse Image call per missing file):  cd backend && uv run python ../scripts/generate_images.py [--force]
Writes frontend/public/images/<activity>.jpg and <activity>-<city>.jpg (resized with macOS `sips`).
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ai.imagery import SCENES, photo_prompt  # noqa: E402
from app.ai.muse import MuseClient  # noqa: E402
from app.config import get_settings  # noqa: E402

# Activity + city pairs used by the demo plans; keep in sync with CITY_ACTIVITY_PHOTOS in frontend Brand.tsx.
PAIRS = [("conference", "Philadelphia"), ("travel", "Philadelphia"), ("study", "Philadelphia"),
         ("event", "Philadelphia"), ("hackathon", "Austin")]


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "frontend/public/images"
    out.mkdir(parents=True, exist_ok=True)
    client = MuseClient(get_settings())
    if not client.ai_live:
        sys.exit("MODEL_API_KEY is not set.")
    jobs = {a: photo_prompt(a, "a typical US city") for a in SCENES}
    jobs |= {f"{a}-{c.lower()}": photo_prompt(a, c) for a, c in PAIRS}
    for name, prompt in jobs.items():
        target = out / f"{name}.jpg"
        if target.exists() and "--force" not in sys.argv:
            continue
        image = client.generate_image(prompt)
        raw = out / f"{name}.{image.fmt}"
        raw.write_bytes(image.data)
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "72", "-Z", "1200", str(raw), "--out", str(target)], check=True, capture_output=True)
        raw.unlink()
        print(f"{name}: {target.stat().st_size // 1024} KB", flush=True)


if __name__ == "__main__":
    main()
