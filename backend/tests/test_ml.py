"""Offline ML tests never request the database fixture or change production data."""

import json
import hashlib

import pytest

pytest.importorskip("catboost", reason="Install the optional ml extra to run model tests")
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

from kickpick.ml.features import CLASS_NAMES, FEATURES, FEATURE_VERSION, build_features, model_frame, split_masks
from kickpick.ml.training import Baseline, calibrate, fit_temperature, forecast, metrics, read_dataset


def game(match_id, kickoff, home=1, away=2, score=(1, 0), **extra):
    return {"match_id": match_id, "kickoff": pd.Timestamp(kickoff, tz="UTC"),
            "league": "premier-league", "season": "2023/2024", "status": "FT",
            "home_team_id": home, "away_team_id": away,
            "home_team": str(home), "away_team": str(away),
            "home_score": score[0], "away_score": score[1], **extra}


def test_target_and_future_results_cannot_change_prematch_features():
    source = pd.DataFrame([
        game(1, "2023-01-01 12:00", home_xg=1.2, away_xg=0.3),
        game(2, "2023-01-08 12:00"), game(3, "2023-01-15 12:00"),
    ])
    first = build_features(source)
    changed = source.copy()
    changed.loc[changed.match_id >= 2, ["home_score", "away_score", "home_xg"]] = [0, 9, 10]
    second = build_features(changed)
    pd.testing.assert_frame_equal(model_frame(first.iloc[:2]), model_frame(second.iloc[:2]))
    assert second.iloc[1].target != first.iloc[1].target
    assert first.iloc[2].home_goals_for_5 != second.iloc[2].home_goals_for_5


def test_result_availability_strict_tie_and_missing_xg():
    source = pd.DataFrame([
        game(1, "2023-01-01 12:00"),  # available Jan 1 15:00
        game(2, "2023-01-02 15:00"),  # prediction Jan 1 15:00; exact tie excluded
        game(3, "2023-01-02 15:01"),
    ])
    frame = build_features(source)
    assert frame.iloc[1].home_history_games == 0
    assert frame.iloc[2].home_history_games == 1
    assert frame.iloc[2].home_xg_count_5 == 0
    assert np.isnan(frame.iloc[2].home_xg_for_5)
    assert frame.iloc[2].home_latest_available_at < frame.iloc[2].prediction_time


def test_same_competition_across_seasons_and_team_orientation():
    source = pd.DataFrame([
        game(1, "2022-05-01", score=(3, 1), home_xg=2.5, away_xg=0.8),
        game(2, "2022-08-01", home=2, away=1, season="2022/2023"),
        game(3, "2022-09-01", league="laliga"),
    ])
    frame = build_features(source)
    assert frame.iloc[1].home_goals_for_5 == 1
    assert frame.iloc[1].home_goals_against_5 == 3
    assert frame.iloc[1].home_xg_for_5 == 0.8
    assert frame.iloc[1].away_points_5 == 3
    assert frame.iloc[2].home_history_games == 0


def test_rolling_window_drops_old_games_and_new_teams_have_no_fabricated_form():
    source = pd.DataFrame([game(i + 1, f"2023-01-{i + 1:02} 12:00", score=(i, 0)) for i in range(10)])
    frame = build_features(source)
    # T-24h excludes yesterday's game, which was not finished at the cutoff.
    assert frame.iloc[-1].home_history_games == 8
    assert frame.iloc[-1].home_goals_for_5 == np.mean([3, 4, 5, 6, 7])
    assert frame.iloc[0].home_elo == 1500
    assert frame.iloc[0].away_elo == 1500


def test_split_boundaries_disjoint_and_feature_allowlist():
    frame = pd.DataFrame({"kickoff": pd.to_datetime([
        "2023-06-30", "2023-07-01", "2024-07-01", "2025-07-01", "2026-07-01"], utc=True),
        "target": [0] * 5, "home_history_games": [5] * 5, "away_history_games": [5] * 5})
    masks = split_masks(frame)
    assert [int(mask.sum()) for mask in masks.values()] == [1, 1, 1, 1]
    assert np.array(list(masks.values())).sum(axis=0).tolist() == [1, 1, 1, 1, 0]
    assert not set(FEATURES) & {"target", "home_score", "away_score", "kickoff", "match_id", "season"}


def test_baselines_json_roundtrip_unknown_teams_and_normalization(tmp_path):
    frame = build_features(pd.DataFrame([
        game(i + 1, f"2023-01-{i + 1:02} 12:00", home=1 + i % 3, away=5 + i % 3,
             score=[(2, 0), (1, 1), (0, 2)][i % 3]) for i in range(15)
    ]))
    unseen = frame.tail(3).copy()
    unseen["home_team_id"] = 999
    for name in ("league_frequency", "elo_logistic", "poisson"):
        fitted = Baseline.fit(name, frame)
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(fitted.state))
        loaded = Baseline(json.loads(path.read_text()))
        probabilities = loaded.predict_proba(unseen)
        np.testing.assert_allclose(probabilities, fitted.predict_proba(unseen))
        assert probabilities.shape == (3, 3)
        assert np.all(probabilities > 0)
        np.testing.assert_allclose(probabilities.sum(axis=1), 1)


def test_catboost_artifact_roundtrip_and_class_order(tmp_path):
    frame = build_features(pd.DataFrame([
        game(i + 1, f"2023-01-{i + 1:02} 12:00", score=[(2, 0), (1, 1), (0, 2)][i % 3])
        for i in range(12)
    ]))
    x = model_frame(frame)
    model = CatBoostClassifier(iterations=3, depth=2, loss_function="MultiClass", thread_count=1,
                               cat_features=["league", "home_team_id", "away_team_id"],
                               allow_writing_files=False, verbose=False)
    model.fit(x, frame["target"].astype(int))
    path = tmp_path / "test.cbm"
    model.save_model(str(path))
    loaded = CatBoostClassifier()
    loaded.load_model(str(path))
    assert loaded.classes_.tolist() == [0, 1, 2]
    np.testing.assert_allclose(loaded.predict_proba(x), model.predict_proba(x))


def test_calibration_and_metric_semantics():
    p = np.array([[0.99, 0.005, 0.005], [0.99, 0.005, 0.005], [0.99, 0.005, 0.005]])
    y = np.array([0, 1, 2])
    temperature = fit_temperature(p, y)
    assert temperature > 1
    assert metrics(y, calibrate(p, temperature))["log_loss"] < metrics(y, p)["log_loss"]
    perfect = metrics(y, np.eye(3))
    assert perfect["brier_sum_3_classes"] == 0
    assert perfect["accuracy"] == 1
    with pytest.raises(ValueError, match="sum to one"):
        metrics(y, p * 0.5)


def test_duplicate_matches_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        build_features(pd.DataFrame([game(1, "2023-01-01"), game(1, "2023-01-08")]))


def test_forecast_freshness_cutoff_and_artifact_integrity(tmp_path):
    frame = build_features(pd.DataFrame([
        *[game(i + 1, f"2023-01-{i + 1:02} 12:00") for i in range(12)],
        game(50, "2023-01-20 12:00", status="NS", score=(None, None)),
        game(51, "2023-01-22 12:00", status="NS", score=(None, None)),
    ]))
    dataset = tmp_path / "features.parquet"
    frame.to_parquet(dataset, index=False)
    manifest = {"feature_version": FEATURE_VERSION, "as_of": "2023-01-19T17:45:00+00:00",
                "features_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest()}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    meta = {"feature_version": FEATURE_VERSION, "features": list(FEATURES),
            "class_order": list(CLASS_NAMES), "champion": "league_frequency", "temperature": 1}
    baseline_path = tmp_path / "league_frequency.json"
    baseline_path.write_text(json.dumps({
        "kind": "league_frequency", "overall": [0.5, 0.25, 0.25], "by_league": {}}))
    meta["model_sha256"] = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    meta["model_version"] = "test-v1"
    (tmp_path / "predictor.json").write_text(json.dumps(meta))
    output = tmp_path / "next.json"
    result = forecast(dataset, tmp_path, output, pd.Timestamp("2023-01-19T18:00:00Z"))
    assert result.match_id.tolist() == [50]
    assert result.iloc[0].prediction_time == pd.Timestamp("2023-01-19T12:00:00Z")
    assert json.loads(output.read_text())[0]["p_H"] == 0.5
    with pytest.raises(ValueError, match="preceding hour"):
        forecast(dataset, tmp_path, output, pd.Timestamp("2023-01-19T19:00:00Z"))
    manifest["features_sha256"] = "incorrect"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="checksum"):
        read_dataset(dataset)
