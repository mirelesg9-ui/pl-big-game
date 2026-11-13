# Big Game

Premier League player analytics that asks: does a player show up against the best teams, or fade?
Every player is judged against what he was *expected* to produce in each fixture, and every verdict comes with an uncertainty range.

## How it works

1. **Data**: per-match FPL data (Opta xG, xA, xG conceded on pitch, defensive contributions) for 2022/23 onward, from the open [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League) archive.
2. **Team strength**: before every match, each team gets a rating from the weighted average of its past xG difference (half-life 12 matches). Opponents are tiered Elite / Strong / Mid / Weak by rank on match day.
3. **Context**: derby/rivalry flags (`pipeline/config.py`), table stakes (title, Europe, relegation races from GW10), home/away, own-team strength.
4. **Expected output**: a pooled model per position group (attack: xG + xA per 90; defence: team xG conceded per 90 on pitch) predicts each player-match from that context.
5. **Big-game effect**: each player's leftover response to opponent strength, estimated *within* each season-and-club stint (so a breakout year or a transfer isn't mistaken for a big-game effect), then shrunk toward zero by empirical Bayes so small samples can't produce extreme verdicts.
6. **Honesty checks** (shown on the site):
   - Reliability: how many matches each stat needs before it's repeatable (split-half r ≥ 0.7, within position).
   - Repeatability: does a player's big-game effect in early seasons predict it in later ones? If not, verdicts are labelled as description, not a trait.
   - Permutation null: the same model on shuffled opponents.
7. **Player vs system**: share of team xG + xA while on the pitch, and team xG conceded with him on vs off, by season and club.

Rates use appearances of 30+ minutes and are ratios of sums.

## Known limits

- FPL xG includes penalties; it isn't split, so a penalty can lift a single match.
- Premier League only: no Champions League or cup games.
- On-ball output and on-pitch team results only. Pressing and off-ball runs aren't in free data.
- The archive can lag the live season by a few weeks.

## Run it

```bash
pip install -r requirements.txt
python pipeline/fetch.py
python pipeline/build.py
cd site && python -m http.server   # open http://localhost:8000
```

GitHub Actions (`.github/workflows/update.yml`) rebuilds every Tuesday and publishes `site/` to GitHub Pages.
