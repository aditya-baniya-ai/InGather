"""Download the public Meetup.com dataset (Liu et al., KDD 2012) used to train the matcher into backend/ml/data/.

    uv run python ml/fetch_data.py

About 700 MB unpacked. The data is not committed; only the trained artifacts in app/ml/artifacts are.
"""

import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

SOURCE = "https://raw.githubusercontent.com/wuyuehit/meetup_dataset/main"
FILES = {
    "meetup_tag/tag_text.csv": "tag_text.csv",
    "meetup_tag/group_tag.csv": "group_tag.csv",
    "meetup_tag/user_tag.csv.zip": "user_tag.csv",
    "meetup_network/user_group.csv.zip": "user_group.csv",
}
DATA = Path(__file__).parent / "data"


def fetch(remote: str, local: str) -> None:
    target = DATA / local
    if target.exists():
        print(f"have {local}")
        return
    print(f"downloading {remote} ...", flush=True)
    with urllib.request.urlopen(f"{SOURCE}/{remote}", timeout=300) as r:
        body = r.read()
    if remote.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            body = z.read(next(n for n in z.namelist() if n.endswith(local) and not n.startswith("__MACOSX")))
    target.write_bytes(body)
    print(f"  {local}: {len(body) / 1e6:.0f} MB sha256={hashlib.sha256(body).hexdigest()[:16]}")


def main() -> int:
    DATA.mkdir(exist_ok=True)
    for remote, local in FILES.items():
        fetch(remote, local)
    return 0


if __name__ == "__main__":
    sys.exit(main())
