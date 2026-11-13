"""Build the PL Big Game dataset.

    python pipeline/fetch.py && python pipeline/build.py

Writes JSON for the site into site/data/:
  players.json        search index
  p/<slug>.json       one file per player (verdict, tiers, system, match log)
  league.json         every player's big-game estimate (funnel plot)
  meta.json           reliability curves, validation results, data date

Method (see README for the reasoning):
  1. Team strength before each match = weighted mean of past xG difference.
  2. Pooled model per position group predicts each player-match's output
     from opponent strength, own-team strength, home, derby and stakes.
  3. Each player's leftover response to opponent strength (a slope) is
     estimated and shrunk toward zero by empirical Bayes, so small samples
     can't produce extreme verdicts.
"""
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as C  # noqa: E402
from fetch import CACHE  # noqa: E402
from sources import club, fold  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data"
Z80 = 1.2816  # two-sided 80% normal interval


# ------------------------------------------------------------------ load

def load():
    frames = []
    for season in C.SEASONS:
        f = CACHE / f"{season}.csv"
        if not f.exists():
            continue
        df = pd.read_csv(f, low_memory=False)
        df["season"] = season
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    for col in ["defensive_contribution", "starts", "clearances_blocks_interceptions",
                "tackles", "goals_conceded"]:
        if col not in df:
            df[col] = np.nan
    num = ["minutes", "goals_scored", "assists", "expected_goals", "expected_assists",
           "expected_goal_involvements", "expected_goals_conceded", "team_h_score",
           "team_a_score", "starts", "defensive_contribution", "GW", "penalties_missed",
           "clearances_blocks_interceptions", "tackles", "goals_conceded"]
    for col in num:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["was_home"] = df["was_home"].astype(str).str.lower().eq("true")
    df["kickoff"] = pd.to_datetime(df["kickoff_time"], utc=True)
    df["position"] = df["position"].replace({"GKP": "GK", "AM": "MID"})
    df = df[df["position"].isin(["GK", "DEF", "MID", "FWD"])].copy()
    # Defender actions an individual owns: clearances, blocks, interceptions, tackles
    # (FPL tracks these from 2025/26).
    df["def_actions"] = df["clearances_blocks_interceptions"] + df["tackles"]
    # Keeper shot-stopping proxy: chances conceded on pitch minus goals let in.
    df["goals_prevented"] = df["expected_goals_conceded"] - df["goals_conceded"]
    df["team"] = df["team"].map(club)
    return df


# -------------------------------------------------------------- fixtures

def build_fixtures(df):
    """One row per match with both teams, score and team xG totals."""
    played = df[df["minutes"] > 0]
    xg = played.groupby(["season", "fixture", "team"]).agg(
        xg=("expected_goals", "sum"), xa=("expected_assists", "sum")).reset_index()
    meta = df.groupby(["season", "fixture", "team"]).agg(
        home=("was_home", "first"), kickoff=("kickoff", "first"), gw=("GW", "first"),
        hs=("team_h_score", "first"), as_=("team_a_score", "first")).reset_index()
    t = meta.merge(xg, on=["season", "fixture", "team"], how="left").fillna({"xg": 0, "xa": 0})
    h = t[t["home"]].rename(columns={"team": "home_team", "xg": "home_xg", "xa": "home_xa"})
    a = t[~t["home"]][["season", "fixture", "team", "xg", "xa"]].rename(
        columns={"team": "away_team", "xg": "away_xg", "xa": "away_xa"})
    fx = h.merge(a, on=["season", "fixture"])
    fx = fx.rename(columns={"hs": "home_goals", "as_": "away_goals"}).drop(columns="home")
    fx = fx.dropna(subset=["home_goals"]).sort_values("kickoff").reset_index(drop=True)
    return fx


def team_strength(fx):
    """Pre-match strength for both sides: EW mean of past xG difference."""
    decay = 0.5 ** (1 / C.STRENGTH_HALFLIFE)
    state = {}  # team -> (weighted sum, weight)
    hs, as_ = [], []
    for r in fx.itertuples():
        for team, out in ((r.home_team, hs), (r.away_team, as_)):
            s, w = state.get(team, (C.PROMOTED_PRIOR * C.PRIOR_WEIGHT, C.PRIOR_WEIGHT))
            out.append(s / w)
        for team, xgd in ((r.home_team, r.home_xg - r.away_xg), (r.away_team, r.away_xg - r.home_xg)):
            s, w = state.get(team, (C.PROMOTED_PRIOR * C.PRIOR_WEIGHT, C.PRIOR_WEIGHT))
            state[team] = (s * decay + xgd, w * decay + 1)
    fx["home_str_xg"], fx["away_str_xg"] = hs, as_
    return fx


def market_strength(fx):
    """Market-implied strength from closing odds (football-data.co.uk).

    Each match's 1X2 and over/under-2.5 prices become expected goals for each
    side (Poisson). Supremacy minus home advantage splits the gap between the
    two clubs around their running market ratings, so the number reflects
    injuries and line-ups known on match day.
    """
    frames = []
    for season in fx.season.unique():
        f = CACHE / f"odds-{season}.csv"
        if not f.exists():
            continue
        o = pd.read_csv(f, encoding="latin-1", on_bad_lines="skip")
        o["season"] = season
        frames.append(o)
    fx["home_str_mkt"] = np.nan
    fx["away_str_mkt"] = np.nan
    if not frames:
        return fx, []
    o = pd.concat(frames, ignore_index=True).dropna(subset=["HomeTeam"])

    def first(cols):
        out = pd.Series(np.nan, index=o.index)
        for c in cols:
            if c in o:
                out = out.fillna(pd.to_numeric(o[c], errors="coerce"))
        return out
    h, d, a = (first([f"PSC{x}", f"AvgC{x}", f"B365C{x}", f"PS{x}", f"Avg{x}", f"B365{x}"]) for x in "HDA")
    ov = first(["PC>2.5", "AvgC>2.5", "P>2.5", "Avg>2.5", "B365>2.5"])
    un = first(["PC<2.5", "AvgC<2.5", "P<2.5", "Avg<2.5", "B365<2.5"])
    tot = 1 / h + 1 / d + 1 / a
    ph, pa = (1 / h) / tot, (1 / a) / tot
    pov = (1 / ov) / (1 / ov + 1 / un)

    lh_flat, la_flat, T_h, T_a, T_o = poisson_table()
    sup = np.full(len(o), np.nan)
    ok = (ph.notna() & pa.notna() & pov.notna()).values
    for i in np.where(ok)[0]:
        j = np.argmin((T_h - ph.iloc[i]) ** 2 + (T_a - pa.iloc[i]) ** 2 + (T_o - pov.iloc[i]) ** 2)
        sup[i] = lh_flat[j] - la_flat[j]
    o["sup"] = sup
    o["home_team"], o["away_team"] = o.HomeTeam.map(club), o.AwayTeam.map(club)
    o = o.dropna(subset=["sup"]).drop_duplicates(["season", "home_team", "away_team"])
    m = fx.merge(o[["season", "home_team", "away_team", "sup"]],
                 on=["season", "home_team", "away_team"], how="left")
    if m.sup.notna().sum() == 0:
        return fx, []
    home_adv = np.nanmean(m.sup)

    decay = 0.5 ** (1 / 8)
    state = {}
    hs, as_ = [], []
    for r in m.itertuples():
        if np.isnan(r.sup):
            hs.append(np.nan)
            as_.append(np.nan)
            continue
        rh = state.get(r.home_team, (r.home_str_xg, 1.0))
        ra = state.get(r.away_team, (r.away_str_xg, 1.0))
        Rh, Ra = rh[0] / rh[1], ra[0] / ra[1]
        gap = (r.sup - home_adv) - (Rh - Ra)
        sh, sa = Rh + gap / 2, Ra - gap / 2
        hs.append(sh)
        as_.append(sa)
        state[r.home_team] = (rh[0] * decay + sh, rh[1] * decay + 1)
        state[r.away_team] = (ra[0] * decay + sa, ra[1] * decay + 1)
    fx["home_str_mkt"], fx["away_str_mkt"] = hs, as_
    return fx, sorted(m.loc[m.sup.notna(), "season"].unique().tolist())


def poisson_table():
    """P(home win), P(away win), P(over 2.5) on a grid of expected goals."""
    lam = np.arange(0.15, 4.5, 0.025)
    LH, LA = np.meshgrid(lam, lam, indexing="ij")
    k = np.arange(11)
    fact = np.cumprod(np.r_[1, np.arange(1, 11)]).astype(float)
    PH = np.exp(-LH)[..., None] * LH[..., None] ** k / fact
    PA = np.exp(-LA)[..., None] * LA[..., None] ** k / fact
    hi, ai = np.meshgrid(k, k, indexing="ij")
    T_h = np.einsum("xyi,xyj,ij->xy", PH, PA, (hi > ai).astype(float)).ravel()
    T_a = np.einsum("xyi,xyj,ij->xy", PH, PA, (hi < ai).astype(float)).ravel()
    T_o = np.einsum("xyi,xyj,ij->xy", PH, PA, (hi + ai > 2).astype(float)).ravel()
    return LH.ravel(), LA.ravel(), T_h, T_a, T_o


def blend_and_rank(fx):
    """Final strength = 70% market, 30% xG (xG alone where odds are missing)."""
    for side in ("home", "away"):
        mk, xg = fx[f"{side}_str_mkt"], fx[f"{side}_str_xg"]
        fx[f"{side}_str"] = np.where(mk.notna(), 0.7 * mk + 0.3 * xg, xg)

    # Each team starts the season at its first pre-match rating (carried over).
    long = pd.concat([
        fx[["season", "kickoff", "home_team", "home_str"]].set_axis(["season", "kickoff", "team", "str"], axis=1),
        fx[["season", "kickoff", "away_team", "away_str"]].set_axis(["season", "kickoff", "team", "str"], axis=1)])
    first = long.sort_values("kickoff").groupby(["season", "team"]).str.first()
    hr, ar = [], []
    cur, latest = None, {}
    for r in fx.itertuples():
        if r.season != cur:
            cur = r.season
            latest = first.loc[cur].to_dict()
        latest[r.home_team], latest[r.away_team] = r.home_str, r.away_str
        vals = latest.values()
        hr.append(1 + sum(v > r.home_str for v in vals))
        ar.append(1 + sum(v > r.away_str for v in vals))
    fx["home_rank"], fx["away_rank"] = hr, ar
    return fx


def table_stakes(fx):
    """Flag matches where either side is in a title, Europe or relegation race."""
    flags = []
    pts = defaultdict(int)
    cur = None
    for r in fx.itertuples():
        if r.season != cur:
            cur, pts = r.season, defaultdict(int)
        stake = False
        if r.gw >= C.STAKES_FROM_GW and len(pts) >= 18:
            table = sorted(pts.values(), reverse=True)
            first, fifth = table[0], table[4]
            eighteenth = table[17] if len(table) > 17 else table[-1]
            for t in (r.home_team, r.away_team):
                p = pts[t]
                if (first - p <= C.TITLE_GAP or abs(p - fifth) <= C.EUROPE_GAP
                        or abs(p - eighteenth) <= C.RELEGATION_GAP):
                    stake = True
        flags.append(stake)
        hg, ag = r.home_goals, r.away_goals
        pts[r.home_team] += 3 if hg > ag else 1 if hg == ag else 0
        pts[r.away_team] += 3 if ag > hg else 1 if hg == ag else 0
    fx["stakes"] = flags
    riv = {frozenset(p) for p in C.RIVALRIES}
    fx["derby"] = [frozenset((h, a)) in riv for h, a in zip(fx.home_team, fx.away_team)]
    return fx


# ------------------------------------------------------- player-match rows

def player_matches(df, fx):
    side = []
    for r in fx.itertuples():
        common = dict(season=r.season, fixture=r.fixture, derby=r.derby, stakes=r.stakes,
                      kickoff=r.kickoff, gw=r.gw)
        side.append(dict(common, team=r.home_team, opp=r.away_team, own_str=r.home_str,
                         opp_str=r.away_str, opp_rank=r.away_rank, team_xg=r.home_xg,
                         team_xa=r.home_xa, team_xga=r.away_xg, gf=r.home_goals, ga=r.away_goals))
        side.append(dict(common, team=r.away_team, opp=r.home_team, own_str=r.away_str,
                         opp_str=r.home_str, opp_rank=r.home_rank, team_xg=r.away_xg,
                         team_xa=r.away_xa, team_xga=r.home_xg, gf=r.away_goals, ga=r.home_goals))
    sides = pd.DataFrame(side)
    pm = df.merge(sides.drop(columns=["kickoff", "gw"]), on=["season", "fixture", "team"], how="inner")
    pm["tier"] = "Weak"
    for name, lo, hi in C.TIERS:
        pm.loc[pm.opp_rank.between(lo, hi), "tier"] = name
    pm["slug"] = pm["name"].map(slugify)
    pm, pen_seasons = remove_penalties(pm)
    pm["xgi"] = pm["npxg"] + pm["expected_assists"]
    return pm, sides, pen_seasons


PEN_XG = 0.76  # value of a penalty in Opta-style xG models


def remove_penalties(pm):
    """npxG = xG - 0.76 per penalty taken. Penalty goals come from ESPN
    (matched to the scorer by name within that match); misses from FPL."""
    pm["pens"] = pm["penalties_missed"].fillna(0)
    seasons = []
    for season in pm.season.unique():
        f = CACHE / f"pens-{season}.json"
        if not f.exists():
            continue
        seasons.append(season)
        sp = pm[(pm.season == season) & (pm.goals_scored > 0)]
        for pen in json.loads(f.read_text())["pens"]:
            if not pen.get("player"):
                continue
            rows = sp[((sp.team == pen["home"]) & (sp.opp == pen["away"]) & sp.was_home) |
                      ((sp.team == pen["away"]) & (sp.opp == pen["home"]) & ~sp.was_home)]
            if pen.get("team"):
                rows = rows[rows.team == pen["team"]]
            who = set(fold(pen["player"]).split())
            hit = [i for i, n in zip(rows.index, rows.name) if who & set(fold(n).split())]
            if len(hit) == 1:
                pm.loc[hit[0], "pens"] += 1
    pm["npxg"] = (pm["expected_goals"] - PEN_XG * pm["pens"]).clip(lower=0)
    return pm, sorted(seasons)



def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ------------------------------------------------------------- the model

GROUPS = {
    "attack": {"positions": ["MID", "FWD"], "metric": "xgi", "label": "npxG + xA per 90",
               "short": "npxGI/90", "better": "higher",
               "words": ("Steps up vs elite", "Fades vs elite")},
    "defence": {"positions": ["DEF"], "metric": "def_actions",
                "label": "clearances, blocks, interceptions + tackles per 90",
                "short": "Def. actions/90", "better": "higher",
                "words": ("Busier than expected vs elite", "Quieter than expected vs elite")},
    "keeper": {"positions": ["GK"], "metric": "goals_prevented",
               "label": "goals prevented per 90 (xG conceded minus goals)",
               "short": "Goals prevented/90", "better": "higher",
               "words": ("Steps up vs elite", "Fades vs elite")},
}


def fit_group(pm, group):
    g = GROUPS[group]
    d = pm[pm.position.isin(g["positions"]) & (pm.minutes >= C.MIN_MINUTES)
           & pm[g["metric"]].notna()].copy()
    d["y"] = d[g["metric"]] / d["minutes"] * 90
    d["w"] = d["minutes"] / 90
    X = np.column_stack([np.ones(len(d)), d.opp_str, d.own_str, d.was_home,
                         d.derby.astype(float), d.stakes.astype(float)])
    sw = np.sqrt(d.w.values)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], d.y.values * sw, rcond=None)
    d["pred_pool"] = X @ beta
    d["r"] = d.y - d.pred_pool
    sigma2 = np.average(d.r ** 2, weights=d.w)  # per-90 noise variance at w=1

    elite_opp = pm.opp_str.quantile(C.ELITE_PCTL)
    mean_opp = pm.opp_str.mean()
    span = elite_opp - mean_opp

    # A player's level is allowed to change every stint (season x team), so a
    # breakout season or a transfer isn't mistaken for a big-game effect. The
    # slope is estimated from variation in opponent strength WITHIN stints.
    d["stint"] = d.season + "|" + d.team
    gw_ = d.groupby(["slug", "stint"])
    wsum = gw_.w.transform("sum")
    d["level"] = (d.r * d.w).groupby([d.slug, d.stint]).transform("sum") / wsum
    d["x_c"] = d.opp_str - (d.opp_str * d.w).groupby([d.slug, d.stint]).transform("sum") / wsum
    d["r_c"] = d.r - d.level

    rows = []
    for slug, p in d.groupby("slug"):
        w, xc, rc = p.w.values, p.x_c.values, p.r_c.values
        n_stints = p.stint.nunique()
        dof = len(p) - n_stints - 1
        sxx = np.sum(w * xc ** 2)
        if w.sum() < 5 or dof < 4 or sxx <= 1e-9:
            continue
        slope = np.sum(w * xc * rc) / sxx
        s2 = np.sum(w * (rc - slope * xc) ** 2) / dof
        s2 = (dof * s2 + 20 * sigma2) / (dof + 20)   # steady noisy variances
        rows.append(dict(slug=slug, raw_slope=slope, se2=s2 / sxx, n=len(p),
                         minutes=p.minutes.sum(),
                         elite_min=p.loc[p.tier == "Elite", "minutes"].sum()))
    est = pd.DataFrame(rows)
    # Method-of-moments between-player slope variance (players with real samples),
    # with a small floor so intervals never collapse to a false point.
    big = est[est.minutes >= 1500]
    if len(big) < 20:
        big = est[est.minutes >= 600]
    floor = 0.06 * np.sqrt(sigma2) / span   # never claim more certainty than this
    tau2 = max(np.var(big.raw_slope) - np.mean(big.se2), floor ** 2)
    k = tau2 / (tau2 + est.se2)
    est["slope"] = k * est.raw_slope
    est["slope_sd"] = np.sqrt(tau2 * est.se2 / (tau2 + est.se2))
    est["delta"] = est.slope * span
    est["delta_sd"] = est.slope_sd * span
    est["group"] = group
    info = dict(beta=dict(zip(["intercept", "opp_str", "own_str", "home", "derby", "stakes"],
                              np.round(beta, 4).tolist())),
                tau=float(np.sqrt(tau2)),
                tau_mom=float(np.sqrt(max(0.0, np.var(big.raw_slope) - np.mean(big.se2)))),
                sigma=float(np.sqrt(sigma2)), span=float(span),
                players=int(len(est)))
    return d, est, info


def verdict(row, better, words):
    lo = row.delta - Z80 * row.delta_sd
    hi = row.delta + Z80 * row.delta_sd
    good = lo > 0 if better == "higher" else hi < 0
    bad = hi < 0 if better == "higher" else lo > 0
    text = words[0] if good else words[1] if bad else "No clear difference vs elite"
    conf = next(label for m, label in C.CONF_MINUTES if row.elite_min >= m)
    if row.delta_sd > 0:
        from math import erf, sqrt
        p_up = 0.5 * (1 + erf(row.delta / (row.delta_sd * sqrt(2))))
    else:
        p_up = 0.5
    return dict(text=text, delta=round(row.delta, 3), lo=round(lo, 3), hi=round(hi, 3),
                p_better=round(p_up if better == "higher" else 1 - p_up, 2),
                confidence=conf, elite_minutes=int(row.elite_min),
                elite_matches=None)


# ------------------------------------------------------- player vs system

def system_view(pm, sides, slug):
    p = pm[pm.slug == slug]
    out = []
    for (season, team), s in p.groupby(["season", "team"], sort=False):
        team_games = sides[(sides.season == season) & (sides.team == team)]
        on = s[s.minutes > 0]
        mins = on.minutes.sum()
        if mins < 270:
            continue
        team_xgi_on = ((on.team_xg + on.team_xa) * on.minutes / 90).sum()
        xgc_on = on.expected_goals_conceded.sum()
        merged = team_games.merge(s[["fixture", "minutes", "expected_goals_conceded"]],
                                  on="fixture", how="left").fillna(0)
        off_min = (90 - merged.minutes).clip(lower=0).sum()
        off_xga = (merged.team_xga - merged.expected_goals_conceded).clip(lower=0).sum()
        out.append(dict(
            season=season, team=team, minutes=int(mins),
            xgi90=round(on.xgi.sum() / mins * 90, 3),
            team_share=round(on.xgi.sum() / team_xgi_on, 3) if team_xgi_on else None,
            xgc90_on=round(xgc_on / mins * 90, 3),
            xgc90_off=round(off_xga / off_min * 90, 3) if off_min >= 180 else None))
    return out


# ------------------------------------------------------------ reliability

def reliability(pm):
    """Split-half correlation by matches per half (no Spearman-Brown)."""
    d = pm[pm.minutes >= C.MIN_MINUTES].sort_values("kickoff")
    metrics = {"npxG": "npxg", "xA": "expected_assists", "npxG + xA": "xgi",
               "Defender actions": "def_actions",
               "Keeper goals prevented": "goals_prevented"}
    out = {}
    for label, col in metrics.items():
        dd = d.dropna(subset=[col])
        if label == "Defender actions":
            dd = dd[dd.position == "DEF"]
        elif label == "Keeper goals prevented":
            dd = dd[dd.position == "GK"]
        else:
            dd = dd[dd.position.isin(["MID", "FWD"])]
        curve = []
        for n in range(2, 20):
            a, b, keys = [], [], []
            for _, g in dd.groupby(["slug", "season"]):
                if len(g) < 2 * n:
                    continue
                g = g.iloc[: 2 * n]
                odd, even = g.iloc[0::2], g.iloc[1::2]
                a.append(odd[col].sum() / odd.minutes.sum() * 90)
                b.append(even[col].sum() / even.minutes.sum() * 90)
                keys.append(g.position.iloc[-1])
            if len(a) >= 30:
                # correlate within position (centered), so forwards vs full-backs
                # differences don't flatter the number
                frame = pd.DataFrame(dict(a=a, b=b, k=keys))
                frame[["a", "b"]] -= frame.groupby("k")[["a", "b"]].transform("mean")
                curve.append(dict(matches=n, r=round(float(frame.a.corr(frame.b)), 3),
                                  players=len(a)))
        stable = next((c["matches"] for c in curve if c["r"] >= 0.7), None)
        out[label] = dict(curve=curve, matches_to_0_7=stable)
    return out


# ------------------------------------------------------------- validation

def validate(pm, group, seed=7):
    """Does a player's big-game slope repeat? Early seasons vs later ones,
    plus a permutation null for the between-player variance."""
    metric = GROUPS[group]["metric"]
    seasons = sorted(pm.loc[pm[metric].notna() & pm.position.isin(GROUPS[group]["positions"])
                            & (pm.minutes > 0), "season"].unique())
    half = len(seasons) // 2
    early = pm[pm.season.isin(seasons[:half])]
    late = pm[pm.season.isin(seasons[half:])]
    _, e1, _ = fit_group(early, group)
    _, e2, _ = fit_group(late, group)
    m = e1.merge(e2, on="slug", suffixes=("_a", "_b"))
    m = m[(m.minutes_a >= 900) & (m.minutes_b >= 900)]
    rep = (float(np.corrcoef(m.raw_slope_a, m.raw_slope_b)[0, 1])
           if len(m) > 20 and half > 0 else None)

    _, est, info = fit_group(pm, group)
    rng = np.random.default_rng(seed)
    shuffled = pm.copy()
    shuffled["opp_str"] = shuffled.groupby("slug").opp_str.transform(
        lambda s: rng.permutation(s.values))
    _, _, info_null = fit_group(shuffled, group)
    return dict(repeatability_r=None if rep is None else round(rep, 3), players=int(len(m)),
                tau_real=round(info["tau_mom"], 4), tau_shuffled=round(info_null["tau_mom"], 4))


# ------------------------------------------------------------------ main

def main():
    df = load()
    fx = team_strength(build_fixtures(df))
    fx, odds_seasons = market_strength(fx)
    fx = table_stakes(blend_and_rank(fx))
    pm, sides, pen_seasons = player_matches(df, fx)

    models = {g: fit_group(pm, g) for g in GROUPS}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "p").mkdir(exist_ok=True)

    latest = pm.sort_values("kickoff").groupby("slug").tail(1).set_index("slug")
    index, league = [], []
    for slug, p in pm.groupby("slug"):
        mins = int(p.minutes.sum())
        if mins < 450:
            continue
        pos = latest.loc[slug, "position"]
        group = {"DEF": "defence", "GK": "keeper"}.get(pos, "attack")
        g = GROUPS[group]
        d, est, info = models[group]
        e = est[est.slug == slug]
        ver = verdict(e.iloc[0], g["better"], g["words"]) if len(e) else None
        if ver:
            ver["elite_matches"] = int((d[d.slug == slug].tier == "Elite").sum())
            dp_ = d[d.slug == slug]
            league.append(dict(slug=slug, name=p.name.iloc[0], pos=pos, group=group,
                               base=round(float(np.average(dp_.y, weights=dp_.w)), 3),
                               team=latest.loc[slug, "team"], **{k: ver[k] for k in
                               ("delta", "lo", "hi", "elite_minutes", "text", "confidence", "p_better")}))

        # Tier table: actual vs expected (pooled model + player's own level).
        dp = d[d.slug == slug]
        tiers = []
        for name, *_ in C.TIERS:
            t = dp[dp.tier == name]
            if t.w.sum() == 0:
                tiers.append(dict(tier=name, matches=0))
                continue
            tiers.append(dict(tier=name, matches=int(len(t)), minutes=int(t.minutes.sum()),
                              actual=round(float(np.average(t.y, weights=t.w)), 3),
                              expected=round(float(np.average(t.pred_pool + t.level, weights=t.w)), 3)))

        log = p.sort_values("kickoff", ascending=False)
        matches = [dict(date=r.kickoff.strftime("%Y-%m-%d"), season=r.season, gw=int(r.GW),
                        team=r.team, opp=r.opp, home=bool(r.was_home), tier=r.tier,
                        derby=bool(r.derby), stakes=bool(r.stakes), minutes=int(r.minutes),
                        started=None if pd.isna(r.starts) else bool(r.starts),
                        score=f"{int(r.gf)}-{int(r.ga)}", goals=int(r.goals_scored),
                        assists=int(r.assists), xg=round(r.expected_goals, 2),
                        xa=round(r.expected_assists, 2), npxg=round(r.npxg, 2),
                        pens=int(r.pens),
                        da=None if pd.isna(r.def_actions) else int(r.def_actions),
                        gp=None if pd.isna(r.goals_prevented) else round(r.goals_prevented, 2),
                        xgc=round(r.expected_goals_conceded, 2),
                        defcon=None if pd.isna(r.defensive_contribution) else int(r.defensive_contribution))
                   for r in log.itertuples()]

        doc = dict(slug=slug, name=p.name.iloc[0], position=pos, group=group,
                   metric=g["label"], short=g["short"], better=g["better"], minutes=mins,
                   teams=list(dict.fromkeys(p.sort_values("kickoff").team)),
                   verdict=ver, tiers=tiers, system=system_view(pm, sides, slug),
                   matches=matches)
        (OUT / "p" / f"{slug}.json").write_text(json.dumps(doc, separators=(",", ":")))
        index.append(dict(slug=slug, name=doc["name"], pos=pos, team=latest.loc[slug, "team"],
                          minutes=mins))

    index.sort(key=lambda x: -x["minutes"])
    (OUT / "players.json").write_text(json.dumps(index, separators=(",", ":")))
    (OUT / "league.json").write_text(json.dumps(league, separators=(",", ":")))

    meta = dict(
        built=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        last_match=pm.kickoff.max().strftime("%Y-%m-%d"),
        seasons=sorted(pm.season.unique().tolist()),
        sources=dict(odds=odds_seasons, penalties=pen_seasons),
        models={g: m[2] for g, m in models.items()},
        reliability=reliability(pm),
        validation={g: validate(pm, g) for g in GROUPS},
    )
    # A "big-game player" label is only meaningful if the effect repeats from
    # one set of seasons to the next. Below this bar the app shows verdicts as
    # description, not as a trait.
    for g, v in meta["validation"].items():
        v["trait_supported"] = bool(v["repeatability_r"] is not None and v["repeatability_r"] >= 0.3)
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1))
    print(f"{len(index)} players, last match {meta['last_match']}")
    print(json.dumps({k: meta[k] for k in ("models", "validation")}, indent=1))


if __name__ == "__main__":
    main()
