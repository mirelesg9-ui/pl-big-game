"""Extra data sources. Each one caches to cache/ and fails soft: if a site is
down, the build carries on without it and says so in meta.json.

  live FPL API      current season, up to the latest finished gameweek
  football-data     closing betting odds -> market-implied team strength
  ESPN scoreboard   which goals were penalties -> non-penalty xG
"""
import csv
import io
import json
from pathlib import Path
import sys
import time
import unicodedata
import urllib.request

sys.path.insert(0, str(Path(__file__).parent))
from config import SEASONS  # noqa: E402

CACHE = Path(__file__).resolve().parent.parent / "cache"
UA = {"User-Agent": "Mozilla/5.0 (pl-big-game; github.com/mirelesg9-ui/pl-big-game)"}

# Every outside spelling of a club -> the FPL name used everywhere else.
ALIASES = {
    "manchester united": "Man Utd", "man united": "Man Utd", "man utd": "Man Utd",
    "manchester city": "Man City", "man city": "Man City",
    "tottenham": "Spurs", "tottenham hotspur": "Spurs", "spurs": "Spurs",
    "nottingham forest": "Nott'm Forest", "nott'm forest": "Nott'm Forest", "nottm forest": "Nott'm Forest",
    "newcastle": "Newcastle", "newcastle united": "Newcastle",
    "wolves": "Wolves", "wolverhampton": "Wolves", "wolverhampton wanderers": "Wolves",
    "brighton": "Brighton", "brighton & hove albion": "Brighton", "brighton and hove albion": "Brighton",
    "sheffield united": "Sheffield Utd", "sheffield utd": "Sheffield Utd",
    "west ham": "West Ham", "west ham united": "West Ham",
    "leeds": "Leeds", "leeds united": "Leeds",
    "leicester": "Leicester", "leicester city": "Leicester",
    "luton": "Luton", "luton town": "Luton",
    "ipswich": "Ipswich", "ipswich town": "Ipswich",
    "bournemouth": "Bournemouth", "afc bournemouth": "Bournemouth",
    "arsenal": "Arsenal", "aston villa": "Aston Villa", "brentford": "Brentford",
    "burnley": "Burnley", "chelsea": "Chelsea", "crystal palace": "Crystal Palace",
    "everton": "Everton", "fulham": "Fulham", "liverpool": "Liverpool",
    "southampton": "Southampton", "sunderland": "Sunderland",
}


def club(name):
    return ALIASES.get(str(name).strip().lower(), str(name).strip())


def fold(s):
    """Lower-case, accents stripped: 'Diego Gómez' -> 'diego gomez'."""
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def get(url, tries=3, pause=1.0):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(pause * (i + 1))
    return None


# ------------------------------------------------------------ live FPL API

FPL = "https://fantasy.premierleague.com/api"
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
FIELDS = ["name", "position", "team", "element", "fixture", "opponent_team", "was_home",
          "minutes", "starts", "goals_scored", "assists", "expected_goals", "expected_assists",
          "expected_goal_involvements", "expected_goals_conceded", "goals_conceded",
          "team_h_score", "team_a_score", "kickoff_time", "GW", "penalties_missed",
          "clearances_blocks_interceptions", "tackles", "recoveries", "defensive_contribution"]


def live_rows(bootstrap, summaries):
    """Turn FPL API payloads into rows shaped like the archive's merged_gw.csv."""
    teams = {t["id"]: t["name"] for t in bootstrap["teams"]}
    rows = []
    for el in bootstrap["elements"]:
        hist = summaries.get(el["id"], [])
        for h in hist:
            row = {k: h.get(k) for k in FIELDS}
            row.update(name=f'{el["first_name"]} {el["second_name"]}', position=POS[el["element_type"]],
                       team=teams[el["team"]], element=el["id"], GW=h.get("round"))
            rows.append(row)
    return rows


def fetch_live_fpl(season=SEASONS[-1]):
    """Write cache/<season>.csv from the live API. Returns True on success."""
    try:
        boot = json.loads(get(f"{FPL}/bootstrap-static/"))
        summaries = {}
        for el in boot["elements"]:
            if el.get("minutes", 0) <= 0:
                continue
            data = json.loads(get(f"{FPL}/element-summary/{el['id']}/"))
            summaries[el["id"]] = data.get("history", [])
            time.sleep(0.15)
        rows = live_rows(boot, summaries)
        if not rows:
            return False
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
        (CACHE / f"{season}.csv").write_text(buf.getvalue())
        print(f"live FPL: {len(rows)} player-matches for {season}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"live FPL unavailable ({e}); keeping archive data")
        return False


# ------------------------------------------------------------ betting odds

def fd_code(season):  # "2024-25" -> "2425"
    a, b = season.split("-")
    return a[2:] + b


def fetch_odds():
    """Download football-data.co.uk Premier League results + odds per season."""
    got = []
    for i, season in enumerate(SEASONS):
        out = CACHE / f"odds-{season}.csv"
        if out.exists() and i < len(SEASONS) - 1:
            got.append(season)
            continue
        try:
            out.write_bytes(get(f"https://www.football-data.co.uk/mmz4281/{fd_code(season)}/E0.csv"))
            got.append(season)
        except Exception as e:  # noqa: BLE001
            print(f"odds {season} unavailable ({e})")
            if out.exists():
                got.append(season)
    return got


# ---------------------------------------------------------- ESPN penalties

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"


def fetch_penalties(dates_by_season):
    """{season: [YYYYMMDD,...]} -> cache/pens-<season>.json listing every
    penalty goal as {home, away, team, player}. Past seasons fetched once."""
    done = []
    for i, season in enumerate(SEASONS):
        out = CACHE / f"pens-{season}.json"
        current = i == len(SEASONS) - 1
        known = json.loads(out.read_text()) if out.exists() else {"dates": [], "pens": []}
        todo = [d for d in dates_by_season.get(season, []) if d not in known["dates"]]
        if not todo and out.exists():
            done.append(season)
            continue
        try:
            for d in todo:
                data = json.loads(get(f"{ESPN}?dates={d}"))
                for ev in data.get("events", []):
                    comp = ev["competitions"][0]
                    if comp.get("status", {}).get("type", {}).get("completed") is False:
                        continue
                    sides = {c["homeAway"]: c for c in comp["competitors"]}
                    ids = {c["team"]["id"]: club(c["team"].get("shortDisplayName") or c["team"]["displayName"])
                           for c in comp["competitors"]}
                    home = club(sides["home"]["team"].get("shortDisplayName") or sides["home"]["team"]["displayName"])
                    away = club(sides["away"]["team"].get("shortDisplayName") or sides["away"]["team"]["displayName"])
                    for det in comp.get("details", []):
                        if det.get("penaltyKick") and det.get("scoringPlay") and not det.get("ownGoal"):
                            who = (det.get("athletesInvolved") or [{}])[0].get("displayName")
                            known["pens"].append(dict(home=home, away=away, player=who,
                                                      team=ids.get(det.get("team", {}).get("id"))))
                known["dates"].append(d)
                time.sleep(0.1)
            out.write_text(json.dumps(known))
            done.append(season)
        except Exception as e:  # noqa: BLE001
            print(f"ESPN penalties {season} incomplete ({e})")
            if known["dates"]:
                out.write_text(json.dumps(known))
            if not current and out.exists():
                done.append(season)
    return done
