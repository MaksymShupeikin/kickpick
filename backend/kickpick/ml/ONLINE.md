# Prediction service

How to run the persistent prediction service, update the model and read the forecast quality report, for developers and operators of the ML module.

The Compose profile `ml` starts a separate `predictor` service. Every 10 minutes it reconciles previously stored forecasts with finished matches and creates the missing forecasts for matches 1–24 hours ahead. When there are no new matches, the history is not exported again. There is no training inside the service and no training in API requests.

## Updating the model

From `backend/`, after the usual `export` and the first `train` experiment:

```bash
.venv-ml/bin/python -m kickpick.ml refit \
  --dataset artifacts/datasets/first-run/features.parquet \
  --template artifacts/models/first-run/report.json \
  --output artifacts/models/online-v1 --threads 2
```

`refit` fixes the model, depth and number of trees chosen in the first experiment; the weights are trained on more recent history. The last 180 days are used only for calibration. At the boundary, the 24-hour horizon and the 3-hour result availability delay are removed. There is no new parameter search against the test set that has already been viewed.

`predictor.json`, `refit.json`, CatBoost and the JSON comparison models are saved. **The independent quality of the new weights is not yet known.** The old 51.5% does not apply to them: they will be checked on real, published future forecasts.

## Running from the project root

```bash
python3 backend/tools/init_secrets.py
docker compose stop api collector predictor
ML_MODEL_DIR=./backend/artifacts/models/online-v1 docker compose --profile ml up -d --build
```

Specify the actual model directory. The current local candidate is in `backend/artifacts/models/2026-10-16-online-v1`; this is also the Compose default. `init_secrets.py` creates the missing `predictor_db_password` and keeps existing passwords. The applications must be stopped before `db-init`, which assigns owners and permissions. The `pgdata` volume is kept. If `predictor` is already running, stop it too before the next `db-init`. A normal run without forecasts does not need the `ml` profile.

The service runs as UID 10001, with a read-only filesystem and the model on a read-only mount. Limits: 2 CPU, 1 GB RAM; the report is written to a separate `prediction_reports` volume. After replacing the model, recreate the service: the bundle is loaded once at start.

## Storage and immutability

- `prediction_models`: version, file fingerprints, calibration and training periods.
- `match_predictions`: probabilities of all four models, the feature snapshot, data provenance, observation time and the real publication time.
- `prediction_results`: the separately recorded score, or the reason for exclusion.

There is one record per match / bundle / nominal horizon / original match time. A repeated run keeps the first record. Changing the weights, files or calibration changes the bundle fingerprint and its version. UPDATE/DELETE/TRUNCATE on the history are forbidden by triggers. The exceptions are trusted owner migrations and the admin fixtures of the test database.

The database sets the publication time itself and checks that the match has not started and that its time and teams have not changed. During reconciliation, the score is read from the locked match row. A reschedule or cancellation excludes the original forecast and keeps it in the history; a new forecast can be recorded for the new time. If an already recorded result is corrected later, the report shows the discrepancy and excludes it from the metrics until it is reviewed separately.

The `kickpick_predictor` role can SELECT source data and INSERT only into these three tables; UPDATE/DELETE/DDL are unavailable. The collector does not write to the forecast history. Two narrow SECURITY DEFINER triggers with a fixed search_path lock the source row on behalf of the migrator, so predictor does not get UPDATE on the source tables for locking. The API keeps SELECT-only access. Protection against concurrent workers is provided by a PostgreSQL advisory lock, a unique key, and a run that can be repeated after a failure.

## Forecast timing and quality

The offline experiment reconstructs features at T−24h. The persistent service stores features at the **real moment of observation**. After downtime it does not pass off a late forecast as one published yesterday: the actual horizon is stored.

The report is split by model version and timing group:

- `on_time_24h`: published 24 hours ahead, with a tolerance of ±30 minutes;
- `late`: published later, for example at the first start;
- `early`: published earlier, if that ever appears in the history.

The groups are not mixed. Metrics: LogLoss, Brier, accuracy, calibration and a per-league breakdown for CatBoost, Elo, Poisson and outcome frequencies. When there are no finished matches, the metrics are `null` and the `pending` counter shows that results are awaited. Up to 300 games the status is `collecting`; reaching that threshold does not by itself prove the model is better.

```bash
docker compose logs --tail 30 predictor
docker compose exec -T predictor cat /state/quality.json

# Save a copy locally, using the SELECT-only API role:
cd backend
.venv-ml/bin/python -m kickpick.ml quality --days 180 --output artifacts/reports/online.json
```

## API for the app

`GET /matches/{match_id}/prediction` reads a ready record by index. If there is no forecast or the schedule changed: `{"available": false}`. Unknown match: 404. A successful response has `probabilities.home/draw/away` (0–1), `generated_at`, `feature_cutoff`, `model_version`, `nominal_horizon_hours`, `actual_lead_hours`, `on_time_24h` and `experimental: true`. Features and internal models are not exposed publicly. The shared rate limit and ETag apply. The same object is included in the `prediction` field of the `GET /matches/{id}` response: the iOS match card loads together with the match, with no separate request. For finished or cancelled matches, and when there is no forecast, the field is `null`.

iOS shows the pre-match probabilities under the team form and hides the card after the match finishes or is cancelled. In live play the `Pre-match forecast` caption stays: the probabilities are not recalculated from the current score. Before kick-off, iOS refreshes the page every 10 minutes; around kick-off and in live play, every 15 seconds. Finished and cancelled matches are no longer polled.
