"""Settings for the PL Big Game pipeline. Everything tunable lives here."""

# Seasons with FPL expected-stats (xG/xA/xGC started in 2022/23).
SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26", "2026-27"]

ARCHIVE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"

# Appearances shorter than this are kept in the match log but left out of
# per-90 rates and models (cameos inflate/deflate rates).
MIN_MINUTES = 30

# Team-strength rating: exponentially weighted mean of past xG difference.
STRENGTH_HALFLIFE = 12        # matches
PROMOTED_PRIOR = -0.6         # xGD/match for a team with no PL history
PRIOR_WEIGHT = 6              # how many "matches" the prior counts for

# Opponent tiers by pre-match strength rank among that season's 20 teams.
TIERS = [("Elite", 1, 4), ("Strong", 5, 8), ("Mid", 9, 14), ("Weak", 15, 20)]

# Table stakes (only from this gameweek on; earlier tables are noise).
STAKES_FROM_GW = 10
TITLE_GAP = 6       # within N points of 1st
EUROPE_GAP = 4      # within N points of 5th
RELEGATION_GAP = 4  # within N points of 18th (above or below)

# Derbies and big rivalries, by FPL team name. Order doesn't matter.
RIVALRIES = [
    ("Arsenal", "Spurs"), ("Arsenal", "Chelsea"), ("Chelsea", "Spurs"),
    ("Spurs", "West Ham"), ("Chelsea", "West Ham"), ("Arsenal", "West Ham"),
    ("Chelsea", "Fulham"), ("Fulham", "Brentford"), ("Crystal Palace", "Brighton"),
    ("Liverpool", "Everton"), ("Liverpool", "Man Utd"), ("Man City", "Man Utd"),
    ("Liverpool", "Man City"), ("Newcastle", "Sunderland"), ("Aston Villa", "Wolves"),
    ("Leeds", "Man Utd"), ("Nott'm Forest", "Leicester"), ("Southampton", "Bournemouth"),
    ("Arsenal", "Man Utd"),
]

# Big-game delta is reported for an opponent at this strength percentile
# versus an average one.
ELITE_PCTL = 0.90

# Interval shown in the app.
INTERVAL = 0.80

# Confidence label by minutes against Elite-tier opponents.
CONF_MINUTES = [(1500, "High"), (600, "Medium"), (0, "Low")]
