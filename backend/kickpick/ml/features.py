"""Causal feature generation shared by training and inference.

The DB does not store historical observed_at/finished_at. A result is assumed
available three hours after kickoff. This is an approximation, not a historical
snapshot guarantee; suspended games and later data corrections remain a risk.
"""

from collections import defaultdict, deque
from datetime import timedelta
import math

import numpy as np
import pandas as pd

LEAGUES = ("premier-league", "laliga", "serie-a", "bundesliga", "ligue-1")
CLASS_NAMES = ("H", "D", "A")
HORIZON_HOURS = 24
RESULT_DELAY_HOURS = 3
WINDOWS = (5, 10, 20)
STATS = ("goals_for", "goals_against", "points", "xg_for", "xg_against",
         "shots_for", "shots_against", "shots_on_target_for", "shots_on_target_against",
         "possession", "corners_for", "corners_against")
CATEGORICAL = ("league", "home_team_id", "away_team_id")
NUMERIC = tuple(
    [f"{side}_{stat}_{window}" for side in ("home", "away")
     for window in WINDOWS for stat in STATS]
    + [f"{side}_{stat}_count_{window}" for side in ("home", "away")
       for window in WINDOWS for stat in ("games", "xg", "shots")]
    + [f"{side}_{name}" for side in ("home", "away")
       for name in ("history_games", "days_rest", "elo")]
    + ["elo_diff"]
)
FEATURES = (*CATEGORICAL, *NUMERIC)
FEATURE_VERSION = 1


def _number(value):
    return float(value) if value is not None and pd.notna(value) else float("nan")


def _side_result(game, side):
    other = "away" if side == "home" else "home"
    gf, ga = float(game[f"{side}_score"]), float(game[f"{other}_score"])
    return {
        "kickoff": game["kickoff"],
        "available_at": game["kickoff"] + timedelta(hours=RESULT_DELAY_HOURS),
        "match_id": game["match_id"],
        "goals_for": gf, "goals_against": ga,
        "points": 3.0 if gf > ga else 1.0 if gf == ga else 0.0,
        "xg_for": _number(game.get(f"{side}_xg")),
        "xg_against": _number(game.get(f"{other}_xg")),
        "shots_for": _number(game.get(f"{side}_shots")),
        "shots_against": _number(game.get(f"{other}_shots")),
        "shots_on_target_for": _number(game.get(f"{side}_shots_on_target")),
        "shots_on_target_against": _number(game.get(f"{other}_shots_on_target")),
        "possession": _number(game.get(f"{side}_possession")),
        "corners_for": _number(game.get(f"{side}_corners")),
        "corners_against": _number(game.get(f"{other}_corners")),
    }


def build_features(source: pd.DataFrame, *, live_as_of=None) -> pd.DataFrame:
    """Replay targets at T-24h and results at T+3h; forecasts win exact ties.

    Results of older test matches may update history/Elo for later test matches,
    as in a live rolling forecast. Model parameters are never fitted on test data.
    """
    source = source.copy()
    if source.empty:
        raise ValueError("No matches in source")
    source["kickoff"] = pd.to_datetime(source["kickoff"], utc=True)
    if live_as_of is not None:
        live_as_of = pd.Timestamp(live_as_of)
        if live_as_of.tzinfo is None:
            raise ValueError("Live feature cutoff must include timezone")
    if source["match_id"].duplicated().any():
        raise ValueError("Source contains duplicate matches")
    records = source.sort_values(["kickoff", "match_id"]).to_dict("records")
    events = []
    for game in records:
        kickoff = game["kickoff"]
        cutoff = live_as_of if live_as_of is not None and game["status"] == "NS" else kickoff - timedelta(hours=HORIZON_HOURS)
        if game["status"] == "NS" and cutoff >= kickoff:
            raise ValueError("Cannot generate live features after kickoff")
        events.append((cutoff, 0, game["match_id"], game))
        if game["status"] == "FT":
            if not all(pd.notna(game.get(f"{s}_score")) and game[f"{s}_score"] >= 0
                       for s in ("home", "away")):
                raise ValueError("Finished match has invalid scores")
            events.append((kickoff + timedelta(hours=RESULT_DELAY_HOURS), 1, game["match_id"], game))
    events.sort(key=lambda event: event[:3])
    history = defaultdict(lambda: deque(maxlen=max(WINDOWS)))
    counts = defaultdict(int)
    elo = defaultdict(lambda: 1500.0)
    rows = []
    for event_at, kind, _, game in events:
        keys = [(game["league"], game[f"{s}_team_id"]) for s in ("home", "away")]
        if kind == 1:
            home, away = keys
            expected = 1 / (1 + 10 ** ((elo[away] - elo[home] - 50) / 400))
            actual = 1.0 if game["home_score"] > game["away_score"] else (
                0.5 if game["home_score"] == game["away_score"] else 0.0)
            delta = 20 * (actual - expected)
            elo[home] += delta
            elo[away] -= delta
            for side, key in zip(("home", "away"), keys):
                history[key].append(_side_result(game, side))
                counts[key] += 1
            continue
        row = {k: game.get(k) for k in (
            "match_id", "kickoff", "league", "season", "home_team_id", "away_team_id",
            "home_team", "away_team", "status", "home_score", "away_score")}
        row["prediction_time"] = event_at
        row["target"] = (0 if game["home_score"] > game["away_score"] else
                         1 if game["home_score"] == game["away_score"] else 2
                         ) if game["status"] == "FT" else None
        for side, key in zip(("home", "away"), keys):
            past = list(history[key])
            row[f"{side}_history_games"] = counts[key]
            row[f"{side}_elo"] = elo[key]
            row[f"{side}_latest_history_kickoff"] = past[-1]["kickoff"] if past else None
            row[f"{side}_latest_available_at"] = past[-1]["available_at"] if past else None
            row[f"{side}_days_rest"] = min(60.0, (game["kickoff"] - past[-1]["kickoff"])
                                                         .total_seconds() / 86400) if past else np.nan
            for window in WINDOWS:
                subset = past[-window:]
                for stat in STATS:
                    values = [p[stat] for p in subset if math.isfinite(p[stat])]
                    row[f"{side}_{stat}_{window}"] = sum(values) / len(values) if values else np.nan
                row[f"{side}_games_count_{window}"] = len(subset)
                for stat in ("xg", "shots"):
                    row[f"{side}_{stat}_count_{window}"] = sum(
                        math.isfinite(p[f"{stat}_for"]) and math.isfinite(p[f"{stat}_against"])
                        for p in subset)
        row["elo_diff"] = row["home_elo"] - row["away_elo"] + 50
        rows.append(row)
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("No matches in source")
    for side in ("home", "away"):
        available = pd.to_datetime(result[f"{side}_latest_available_at"], utc=True)
        if (available.notna() & (available >= result["prediction_time"])).any():
            raise ValueError("A feature contains a result unavailable at prediction time")
    return result.sort_values(["kickoff", "match_id"]).reset_index(drop=True)


def model_frame(frame):
    """Explicit allowlist prevents labels, dates, scores and IDs leaking into X."""
    result = frame.loc[:, list(FEATURES)].copy()
    for name in CATEGORICAL:
        result[name] = result[name].astype(str)
    for name in NUMERIC:
        result[name] = pd.to_numeric(result[name], errors="raise").astype(float)
    return result


def split_masks(frame):
    """Four disjoint seasons/periods: tune, calibrate, then one untouched test."""
    dates = pd.to_datetime(frame["kickoff"], utc=True)
    eligible = frame["target"].notna() & (frame["home_history_games"] >= 5) & (frame["away_history_games"] >= 5)
    boundaries = {
        "train": ("2017-07-01", "2023-07-01"),
        "validation": ("2023-07-01", "2024-07-01"),
        "calibration": ("2024-07-01", "2025-07-01"),
        "test": ("2025-07-01", "2026-07-01"),
    }
    return {name: eligible & (dates >= pd.Timestamp(start, tz="UTC")) & (dates < pd.Timestamp(end, tz="UTC"))
            for name, (start, end) in boundaries.items()}
