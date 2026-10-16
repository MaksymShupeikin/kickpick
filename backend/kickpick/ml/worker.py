"""Periodic prospective inference and settlement, independent of HTTP requests."""
import hashlib
import importlib.metadata
import json
import logging
import signal
import threading
import time

import pandas as pd
import psycopg

from kickpick.predictions import publish_prediction, register_model, settle_results
from .bundle import ModelBundle
from .evaluation import quality_report, save_report
from .features import FEATURE_VERSION, LEAGUES, build_features, model_frame
from .source import SOURCE_SQL, connect, read_source

logger = logging.getLogger(__name__)
LOCK = (1752195939, 24)


def run_once(connection, bundle, report_path=None):
    """A session lock prevents overlapping workers/restarts from duplicating work."""
    if not connection.autocommit:
        raise ValueError("Worker connection must use autocommit")
    if not connection.execute("SELECT pg_try_advisory_lock(%s,%s)", LOCK).fetchone()[0]:
        return {"skipped": "another_worker"}
    try:
        register_model(connection, bundle.version, bundle.sha256, bundle.registry_metadata)
        settled = settle_results(connection)
        as_of = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        pending = connection.execute("""
            SELECT m.id FROM matches m JOIN seasons s ON s.id=m.season_id
            JOIN competitions c ON c.id=s.competition_id
            WHERE m.status='NS' AND m.kickoff > %s + interval '1 hour'
              AND m.kickoff <= %s + interval '24 hours'
              AND c.slug = ANY(%s)
              AND NOT EXISTS (SELECT FROM match_predictions p WHERE p.match_id=m.id
                  AND p.model_version=%s AND p.horizon_hours=24 AND p.scheduled_kickoff=m.kickoff)
        """, (as_of, as_of, list(LEAGUES), bundle.version)).fetchall()
        inserted, changed = 0, 0
        if pending:
            raw = read_source(connection, as_of)
            # Live forecasts use the actual observation time, never an invented
            # earlier publication time. Offline T-24h reconstruction is unchanged.
            frame = build_features(raw, live_as_of=as_of)
            ids = {row[0] for row in pending}
            frame = frame[(frame["status"] == "NS") & frame["match_id"].isin(ids)
                          & (frame["home_history_games"] >= 5) & (frame["away_history_games"] >= 5)]
            if len(frame):
                probabilities = bundle.predict_all(frame)
                feature_rows = json.loads(model_frame(frame).to_json(orient="records"))
                source_hash = hashlib.sha256(raw.to_json(orient="records", date_format="iso").encode()).hexdigest()
                provenance = {
                    "source_as_of": as_of.isoformat(), "source_sha256": source_hash,
                    "source_rows": len(raw), "sql_sha256": hashlib.sha256(SOURCE_SQL.encode()).hexdigest(),
                    "feature_version": FEATURE_VERSION, "result_delay_hours_approximation": 3,
                    "cutoff_policy": "actual_live_observation_time", "nominal_horizon_hours": 24,
                    "packages": {name: importlib.metadata.version(name) for name in ("catboost", "numpy", "pandas")},
                }
                for index, row in enumerate(frame.to_dict("records")):
                    comparisons = {name: p[index].tolist() for name, p in probabilities.items()}
                    evidence = provenance | {
                        f"{side}_latest_available_at": (pd.Timestamp(row[f"{side}_latest_available_at"]).isoformat()
                                                        if pd.notna(row[f"{side}_latest_available_at"]) else None)
                        for side in ("home", "away")}
                    try:
                        prediction_id = publish_prediction(
                            connection, match_id=row["match_id"], version=bundle.version, kickoff=row["kickoff"],
                            home_team_id=row["home_team_id"], away_team_id=row["away_team_id"], league=row["league"],
                            feature_cutoff=as_of, probabilities=probabilities[bundle.champion][index],
                            features=feature_rows[index], provenance=evidence, baselines=comparisons,
                        )
                        inserted += prediction_id is not None
                    except psycopg.errors.CheckViolation as error:
                        if error.diag.message_primary != "match changed or already started":
                            raise
                        changed += 1
        if report_path is not None:
            save_report(report_path, quality_report(connection))
        return {"published": inserted, "settled": len(settled), "changed_matches_skipped": changed}
    finally:
        connection.execute("SELECT pg_advisory_unlock(%s,%s)", LOCK)


def run_worker(model_dir, *, interval=600, report_path=None, once=False):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bundle = ModelBundle(model_dir)
    stopped = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopped.set())
    logger.info("Prediction model %s loaded; polling every %ss", bundle.version, interval)
    while not stopped.is_set():
        started = time.monotonic()
        try:
            with connect(writer=True) as connection:
                result = run_once(connection, bundle, report_path)
            logger.info("Prediction cycle: %s; elapsed %.2fs", result, time.monotonic() - started)
        except Exception as error:
            if once:
                raise
            # Avoid dumping connection URLs, SQL parameters or passwords to logs.
            logger.error("Prediction cycle failed (%s); retrying next interval", type(error).__name__)
        if once:
            return
        stopped.wait(interval)
