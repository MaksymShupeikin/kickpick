"""Append-only prediction persistence. This module has no ML dependencies."""
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def register_model(connection, version, sha256, metadata):
    connection.execute(
        "INSERT INTO prediction_models(version,bundle_sha256,metadata) VALUES (%s,%s,%s) "
        "ON CONFLICT (version) DO NOTHING", (version, sha256, Jsonb(metadata)),
    )
    if connection.execute("SELECT bundle_sha256,metadata FROM prediction_models WHERE version=%s", (version,)).fetchone() != (sha256, metadata):
        raise ValueError("An immutable model version already has different contents")


def publish_prediction(connection, *, match_id, version, kickoff, home_team_id, away_team_id,
                       league, feature_cutoff, probabilities, features, provenance, baselines):
    """The INSERT trigger rechecks the match and stamps the real DB publication time."""
    row = connection.execute(
        "INSERT INTO match_predictions(match_id,model_version,horizon_hours,scheduled_kickoff,home_team_id,away_team_id,"
        "league,feature_cutoff,p_home,p_draw,p_away,features,provenance,baselines) "
        "VALUES (%s,%s,24,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (match_id,model_version,horizon_hours,scheduled_kickoff) DO NOTHING RETURNING id",
        (int(match_id), version, kickoff, int(home_team_id), int(away_team_id), league, feature_cutoff,
         *[float(p) for p in probabilities], Jsonb(features), Jsonb(provenance), Jsonb(baselines)),
    ).fetchone()
    return row[0] if row else None


def settle_results(connection):
    """Labels come from locked source rows in the DB trigger, never model output."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("""
            INSERT INTO prediction_results(prediction_id)
            SELECT p.id FROM match_predictions p JOIN matches m ON m.id=p.match_id
            WHERE NOT EXISTS (SELECT FROM prediction_results r WHERE r.prediction_id=p.id)
              AND (m.kickoff <> p.scheduled_kickoff OR m.home_team_id <> p.home_team_id
                   OR m.away_team_id <> p.away_team_id OR m.status='CANC'
                   OR (m.status='FT' AND m.home_score >= 0 AND m.away_score >= 0
                       AND m.kickoff + interval '3 hours' < clock_timestamp()))
            ORDER BY p.id LIMIT 1000
            ON CONFLICT (prediction_id) DO NOTHING RETURNING prediction_id,kind
        """)
        return list(cursor.fetchall())
