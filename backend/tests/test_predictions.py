"""Prospective ledger integrity and real PostgreSQL trigger tests, isolated *_test DB."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import psycopg
import pytest

from kickpick.api import app
from kickpick.predictions import publish_prediction, register_model, settle_results


@pytest.fixture
def ledger(db, engine):
    assert engine.url.database.endswith("_test")
    options = engine.url.translate_connect_args(database="dbname", username="user")
    with psycopg.connect(**options, autocommit=True) as connection:
        connection.execute("INSERT INTO competitions(id,slug,name,kind,search_name) VALUES (47,'premier-league','PL','league','pl')")
        connection.execute("INSERT INTO seasons(id,competition_id,name,is_current) VALUES (1,47,'2026/2027',true)")
        connection.execute("INSERT INTO teams(id,name,short_name,search_name) VALUES (1,'A','A','a'),(2,'B','B','b')")
        kickoff = connection.execute("SELECT clock_timestamp() + interval '23 hours 55 minutes'").fetchone()[0]
        connection.execute("INSERT INTO matches(id,season_id,round,kickoff,home_team_id,away_team_id,status) "
                           "VALUES (1,1,'1',%s,1,2,'NS')", (kickoff,))
        register_model(connection, "test-v1", "0" * 64, {"champion": "catboost"})
        yield connection, kickoff


def publish(connection, kickoff, **changes):
    payload = dict(match_id=1, version="test-v1", kickoff=kickoff, home_team_id=1, away_team_id=2,
                   league="premier-league", feature_cutoff=connection.execute("SELECT clock_timestamp()").fetchone()[0],
                   probabilities=[0.5, 0.3, 0.2], features={"elo_diff": 40.0}, provenance={"source": "test"},
                   baselines={"catboost": [0.5, 0.3, 0.2], "elo_logistic": [0.4, 0.3, 0.3]})
    return publish_prediction(connection, **(payload | changes))


def simulate_past_forecast(connection, kickoff, prediction_id):
    """Only fixture admin may simulate time passing; real writers cannot backdate."""
    past = datetime.now(timezone.utc) - timedelta(days=2)
    with connection.transaction():
        connection.execute("SET LOCAL session_replication_role=replica")
        connection.execute("UPDATE match_predictions SET scheduled_kickoff=%s,generated_at=%s,feature_cutoff=%s WHERE id=%s",
                           (past, past - timedelta(hours=24), past - timedelta(hours=24, seconds=2), prediction_id))
        connection.execute("UPDATE matches SET kickoff=%s,status='FT',home_score=2,away_score=1 WHERE id=1", (past,))


def test_forecast_idempotence_and_database_immutability(ledger):
    connection, kickoff = ledger
    prediction_id = publish(connection, kickoff)
    assert prediction_id
    assert publish(connection, kickoff, probabilities=[0.1, 0.1, 0.8]) is None
    assert connection.execute("SELECT p_home,p_draw,p_away FROM match_predictions").fetchone() == (0.5, 0.3, 0.2)
    for statement in ("UPDATE match_predictions SET p_home=0.8", "DELETE FROM match_predictions",
                      "TRUNCATE match_predictions CASCADE", "UPDATE prediction_models SET bundle_sha256='changed'"):
        with pytest.raises(psycopg.errors.CheckViolation, match="append-only"):
            connection.execute(statement)
    with pytest.raises(ValueError, match="different contents"):
        register_model(connection, "test-v1", "different", {})


def test_started_or_changed_match_and_invalid_probabilities_rejected(ledger):
    connection, kickoff = ledger
    with pytest.raises(psycopg.errors.CheckViolation):
        publish(connection, kickoff, probabilities=[0.5, 0.5, 0.5])
    with pytest.raises(psycopg.errors.CheckViolation):
        publish(connection, kickoff, feature_cutoff=kickoff)
    connection.execute("UPDATE matches SET status='LIVE' WHERE id=1")
    with pytest.raises(psycopg.errors.CheckViolation, match="already started"):
        publish(connection, kickoff)
    connection.execute("UPDATE matches SET status='NS',kickoff=kickoff+interval '1 day' WHERE id=1")
    with pytest.raises(psycopg.errors.CheckViolation, match="match changed"):
        publish(connection, kickoff)


def test_settlement_uses_real_result_only_once_and_forbids_rewriting(ledger):
    connection, kickoff = ledger
    prediction_id = publish(connection, kickoff)
    assert settle_results(connection) == []
    with pytest.raises(psycopg.errors.CheckViolation, match="not ready"):
        connection.execute("INSERT INTO prediction_results(prediction_id,kind,home_score,away_score) VALUES (%s,'finished',9,0)", (prediction_id,))
    simulate_past_forecast(connection, kickoff, prediction_id)
    assert settle_results(connection) == [{"prediction_id": prediction_id, "kind": "finished"}]
    assert settle_results(connection) == []
    assert connection.execute("SELECT home_score,away_score FROM prediction_results").fetchone() == (2, 1)
    connection.execute("UPDATE matches SET home_score=1,away_score=2 WHERE id=1")
    assert settle_results(connection) == []
    assert connection.execute("SELECT home_score,away_score FROM prediction_results").fetchone() == (2, 1)
    with pytest.raises(psycopg.errors.CheckViolation, match="append-only"):
        connection.execute("UPDATE prediction_results SET home_score=1")


def test_postponement_voids_original_and_preserves_new_scheduled_forecast(ledger):
    connection, kickoff = ledger
    prediction_id = publish(connection, kickoff)
    new_kickoff = kickoff + timedelta(days=2)
    connection.execute("UPDATE matches SET kickoff=%s WHERE id=1", (new_kickoff,))
    assert settle_results(connection) == [{"prediction_id": prediction_id, "kind": "void"}]
    assert connection.execute("SELECT reason,home_score FROM prediction_results").fetchone() == ("schedule_or_teams_changed", None)
    assert publish(connection, new_kickoff)
    assert connection.execute("SELECT count(*) FROM match_predictions").fetchone()[0] == 2


def test_cancellation_has_no_label(ledger):
    connection, kickoff = ledger
    prediction_id = publish(connection, kickoff)
    connection.execute("UPDATE matches SET status='CANC' WHERE id=1")
    assert settle_results(connection) == [{"prediction_id": prediction_id, "kind": "void"}]
    assert connection.execute("SELECT reason,home_score,away_score FROM prediction_results").fetchone() == ("cancelled", None, None)


def test_read_only_prediction_api_and_etag(ledger):
    connection, kickoff = ledger
    client = TestClient(app)
    assert client.get("/matches/999/prediction").status_code == 404
    assert client.get("/matches/1/prediction").json() == {"available": False}
    publish(connection, kickoff)
    response = client.get("/matches/1/prediction")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["probabilities"] == {"home": 0.5, "draw": 0.3, "away": 0.2}
    assert "features" not in body and "baselines" not in body
    assert client.get("/matches/1/prediction", headers={"If-None-Match": response.headers["etag"]}).status_code == 304
    connection.execute("UPDATE matches SET kickoff=kickoff+interval '1 day' WHERE id=1")
    assert client.get("/matches/1/prediction").json() == {"available": False}
    assert client.get("/matches/1").json()["prediction"] is None


@pytest.mark.parametrize("status", ["NS", "LIVE", "FT", "CANC"])
def test_match_page_includes_prediction_only_before_completion(ledger, status):
    connection, kickoff = ledger
    client = TestClient(app)
    assert client.get("/matches/1").json()["prediction"] is None
    publish(connection, kickoff)
    connection.execute("UPDATE matches SET status=%s WHERE id=1", (status,))
    page = client.get("/matches/1").json()
    if status in ("NS", "LIVE"):
        assert page["prediction"]["probabilities"] == {"home": 0.5, "draw": 0.3, "away": 0.2}
        assert "features" not in page["prediction"]
        assert page["prediction"] == client.get("/matches/1/prediction").json()
    else:
        assert page["prediction"] is None
        assert client.get("/matches/1/prediction").json() == {"available": False}
