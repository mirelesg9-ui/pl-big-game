"""Download per-gameweek FPL data for every season into cache/.

Source: vaastav/Fantasy-Premier-League (an open archive of the official
FPL API). Re-downloads the current season every run; older seasons are
only fetched once.
"""
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).parent))
from config import ARCHIVE, SEASONS  # noqa: E402

CACHE = Path(__file__).resolve().parent.parent / "cache"


def fetch(force_current=True):
    CACHE.mkdir(exist_ok=True)
    for i, season in enumerate(SEASONS):
        out = CACHE / f"{season}.csv"
        current = i == len(SEASONS) - 1
        if out.exists() and not (current and force_current):
            continue
        url = f"{ARCHIVE}/{season}/gws/merged_gw.csv"
        print(f"downloading {season}")
        with urllib.request.urlopen(url, timeout=60) as r:
            out.write_bytes(r.read())
    return CACHE


if __name__ == "__main__":
    fetch()
