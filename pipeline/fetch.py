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


def penalty_dates():
    """Match dates per season, read from the cached FPL data."""
    import csv
    out = {}
    for season in SEASONS:
        f = CACHE / f"{season}.csv"
        if f.exists():
            with f.open() as fh:
                out[season] = sorted({r["kickoff_time"][:10].replace("-", "")
                                      for r in csv.DictReader(fh) if r.get("kickoff_time")})
    return out


if __name__ == "__main__":
    from sources import fetch_live_fpl, fetch_odds, fetch_penalties
    fetch()                 # archive, every season
    fetch_live_fpl()        # current season straight from FPL (fixes archive lag)
    fetch_odds()            # closing odds for market strength
    fetch_penalties(penalty_dates())  # which goals were penalties
