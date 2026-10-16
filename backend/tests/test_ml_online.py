from datetime import timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("catboost", reason="Install the ml extra")
import numpy as np
import pandas as pd
import psycopg

from kickpick.ml.evaluation import quality_report
from kickpick.ml.features import build_features
from kickpick.ml.worker import LOCK, run_once
from test_predictions import ledger, simulate_past_forecast
from test_ml import game


def test_live_cutoff_uses_actual_observation_time():
    source = pd.DataFrame([
        game(1, "2023-01-04 13:00"),
        game(2, "2023-01-05 12:00", status="NS", score=(None, None)),
    ])
    replay = build_features(source)
    live = build_features(source, live_as_of=pd.Timestamp("2023-01-04T18:00:00Z"))
    assert replay.iloc[-1].home_history_games == 0
    assert live.iloc[-1].home_history_games == 1
    assert live.iloc[-1].prediction_time == pd.Timestamp("2023-01-04T18:00:00Z")


def test_worker_publication_restart_settlement_and_quality(ledger, monkeypatch, tmp_path):
    connection, kickoff = ledger
    for index in range(6):
        connection.execute("INSERT INTO matches(id,season_id,round,kickoff,home_team_id,away_team_id,status,home_score,away_score) "
                           "VALUES (%s,1,'1',%s,1,2,'FT',2,1)", (100 + index, kickoff - timedelta(days=7 * (index + 1))))
    bundle = SimpleNamespace(
        version="worker-test", sha256="1" * 64, metadata={}, registry_metadata={"champion": "catboost"},
        champion="catboost", predict_all=lambda frame: {
            name: np.tile([0.5, 0.3, 0.2], (len(frame), 1)) for name in
            ("catboost", "elo_logistic", "poisson", "league_frequency")},
    )
    path = tmp_path / "quality.json"
    first = run_once(connection, bundle, path)
    assert first["published"] == 1
    row = connection.execute("SELECT id,features,feature_cutoff,generated_at FROM match_predictions").fetchone()
    prediction_id, features, cutoff, generated_at = row
    assert features["home_xg_for_5"] is None
    assert features["home_history_games"] == 6
    assert cutoff <= generated_at < kickoff
    assert path.is_file()
    report = quality_report(connection)
    assert report["groups"][0]["pending"] == 1
    assert report["groups"][0]["metrics"] is None
    # Repeated polls do not need another full historical export after publication.
    monkeypatch.setattr("kickpick.ml.worker.read_source", lambda *_: pytest.fail("unnecessary historical export"))
    assert run_once(connection, bundle)["published"] == 0
    simulate_past_forecast(connection, kickoff, prediction_id)
    assert run_once(connection, bundle)["settled"] == 1
    report = quality_report(connection)
    group = report["groups"][0]
    assert group["cohort"] == "on_time_24h" and group["evaluated"] == 1
    assert group["sample_status"] == "collecting"
    assert group["metrics"]["catboost"]["log_loss"] == pytest.approx(-np.log(0.5))
    connection.execute("UPDATE matches SET home_score=0,away_score=2 WHERE id=1")
    group = quality_report(connection)["groups"][0]
    assert group["revised_results_excluded"] == 1 and group["metrics"] is None
    assert connection.execute("SELECT home_score,away_score FROM prediction_results").fetchone() == (2, 1)


def test_concurrent_worker_is_skipped(ledger, engine):
    connection, _ = ledger
    options = engine.url.translate_connect_args(database="dbname", username="user")
    with psycopg.connect(**options, autocommit=True) as other:
        other.execute("SELECT pg_advisory_lock(%s,%s)", LOCK)
        try:
            assert run_once(connection, None) == {"skipped": "another_worker"}
        finally:
            other.execute("SELECT pg_advisory_unlock(%s,%s)", LOCK)
