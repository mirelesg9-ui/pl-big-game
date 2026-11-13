# Big Game

Premier League player analytics that asks: does a player show up against the best teams, or fade?
Every player is judged against what he was *expected* to produce in each fixture, and every verdict comes with an uncertainty range.

## How it works

1. **Data**: per-match FPL data (Opta xG, xA, xG conceded on pitch, defensive actions) for 2022/23 onward, from the open [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League) archive, topped up each run from the live FPL API so the current season is never behind.
2. **Team strength**: 70% market (closing 1X2 and over/under odds from football-data.co.uk, converted to expected goals with a Poisson model) and 30% xG form (weighted past xG difference). Opponents are tiered Elite / Strong / Mid / Weak by rank on match day.
3. **Penalties removed**: ESPN's scoreboard marks penalty goals; FPL records misses. npxG = xG − 0.76 per penalty taken.
4. **Context**: derby/rivalry flags (`pipeline/config.py`), table stakes (title, Europe, relegation races from GW10), home/away, own-team strength.
5. **Expected output**: a pooled model per position group (attackers: npxG + xA per 90; defenders: clearances, blocks, interceptions + tackles per 90, from 2025/26; keepers: xG conceded minus goals conceded per 90) predicts each player-match from that context.
6. **Big-game effect**: each player's leftover response to opponent strength, estimated *within* each season-and-club stint (so a breakout year or a transfer isn't mistaken for a big-game effect), then shrunk toward zero by empirical Bayes so small samples can't produce extreme verdicts.
7. **Honesty checks** (shown on the site):
   - Reliability: how many matches each stat needs before it's repeatable (split-half r ≥ 0.7, within position).
   - Repeatability: does a player's big-game effect in early seasons predict it in later ones? If not, verdicts are labelled as description, not a trait.
   - Permutation null: the same model on shuffled opponents.
8. **Player vs system**: share of team xG + xA while on the pitch, and team xG conceded with him on vs off, by season and club.

Rates use appearances of 30+ minutes and are ratios of sums.

## Known limits

- If ESPN or football-data is unreachable, the build falls back (xG-only strength, misses-only penalty removal) and the Method page says which seasons are covered.
- Defender actions only exist from 2025/26, so defender verdicts start there. Team defending (xG conceded) is shown as on/off context, not as a defender's score.
- Premier League only: no Champions League or cup games.
- On-ball output and on-pitch team results only. Pressing and off-ball runs aren't in free data.

## Run it

```bash
pip install -r requirements.txt
python pipeline/fetch.py
python pipeline/build.py
cd site && python -m http.server   # open http://localhost:8000
```

GitHub Actions (`.github/workflows/update.yml`) rebuilds every Tuesday and publishes `site/` to GitHub Pages.
