# Match prediction pipeline

How to run the offline ML pipeline that trains home win / draw / away win (H/D/A) probabilities, for developers working on the `kickpick.ml` module. It uses the existing database, with no new scraping and no schema changes.

Supported leagues: Premier League, LaLiga, Serie A, Bundesliga, Ligue 1. Cups are not included, because their final score may include extra time.

## Running the pipeline

From `backend/`, with a local PostgreSQL running:

```bash
UV_PROJECT_ENVIRONMENT=.venv-ml uv sync --frozen --extra ml

.venv-ml/bin/python -m kickpick.ml export \
  --output artifacts/datasets/first-run

.venv-ml/bin/python -m kickpick.ml train \
  --dataset artifacts/datasets/first-run/features.parquet \
  --output artifacts/models/first-run --threads 2

.venv-ml/bin/python -m kickpick.ml forecast \
  --dataset artifacts/datasets/first-run/features.parquet \
  --model artifacts/models/first-run \
  --output artifacts/forecasts/first-run.json

.venv-ml/bin/python -m pytest tests/test_ml.py -q
```

Snapshot and training directory names must be new: the previous experiment is kept for comparison. For fresh forecasts, run `export` again into a new directory and pass it to `forecast` together with the already trained model. The snapshot must be no older than one hour. Forecasts are created only for matches that have not started yet and kick off within the next 24 hours; the model's horizon has not been validated for anything else.

The local export uses `kickpick_api` and `.secrets/api_db_password`, which is a read-only role. For another environment, use `ML_DATABASE_HOST`, `ML_DATABASE_PORT`, `ML_DATABASE_NAME`, `ML_DATABASE_USER`, `ML_DATABASE_PASSWORD_FILE` or `ML_DATABASE_URL`. Passwords and URLs are not written to artifacts. The SQL runs in a single read-only repeatable-read transaction with a 30-second timeout and no parallel workers. The connection is closed before features are computed and training starts.

The ML libraries are a separate optional extra. The regular API image does not install them. `.venv-ml/` and `artifacts/` are excluded from Git. The number of training threads is limited to two by default; measure speed on each server separately.

## How features are built

`source.sql` joins `matches → seasons → competitions` and team names, and parses the numeric values from `matches.details.stats` once. Python then walks the timeline. This lets the same code build both historical and future features without thousands of separate SQL queries. A version of the calculation done entirely with JOIN/LATERAL is also in `tools/prediction_features.sql`.

For each target match, features are fixed at `kickoff - 24 hours`:

- average goals, points, xG, shots, shots on target, possession and corners over the team's last 5 / 10 / 20 games in the same league, carried across seasons;
- the number of available games and statistics; a missing xG stays missing;
- Elo, the Elo difference adjusted for home advantage, and days since the previous game in the league;
- the league and team identifiers as categorical features.

The result of a previous game is treated as available 3 hours after it started. If its time equals the cutoff, the result is not included. New teams without five previous games in the given league are skipped for now; this shows up in the report's coverage. Current tables, final lineups, season aggregates and the target match's score are not in the allowed feature list. Final scores are kept in the dataset only as labels and for training the Poisson baseline.

**History limitation:** the database has no old `observed_at`, `finished_at` or snapshots of rescheduled matches. Late corrections, rescheduled or suspended matches and statistics published later can distort the reconstructed backtest. Checking time boundaries does not remove this uncertainty. To validate before publication, save the source facts and features at the moment of the real forecast, then compare them with the outcome.

## Training and evaluation

| Period | Purpose |
|---|---|
| 2016/17 | Initial form/Elo history |
| 2017/18–2022/23 | Training the weights |
| 2023/24 | CatBoost early stopping and choice of variant/model |
| 2024/25 | Temperature scaling of probabilities |
| 2025/26 | Final independent check after parameters are chosen |
| 2026/27 | Demonstration future forecasts |

The comparison covers league outcome frequencies, a logistic regression on Elo, an independent Poisson model of team attack/defence strength, and CatBoost. For CatBoost, four predefined variants are tried: depths 4/6 and the last 3/6 training seasons. The winner is chosen by validation LogLoss; test is not involved. Baseline models are trained on the whole train set. Weights are not retrained after selection: this is a frozen first experiment, not the final production update schedule.

Test runs sequentially in time: already finished games in the test period may update the form and Elo of later matches. Training weights or calibration on test is forbidden. If new features or parameters are chosen using this test report, a new independent check is required, for example saved forecasts of future matchdays.

Metrics: LogLoss, Brier (sum over the three classes, range 0–2), accuracy of the most likely outcome, calibration and a per-league breakdown. To compare CatBoost with the best baseline on validation, an approximate 95% interval of the LogLoss difference is computed with a bootstrap over weekly blocks. An interval that includes zero means no robust advantage is established by this check. Accuracy does not mean betting profitability.

## Artifacts

- `source.parquet`, `features.parquet`, `manifest.json`: the data snapshot, features, export time, library versions and checksums.
- `catboost.cbm`: the trained CatBoost model; the simple models are JSON files with coefficients.
- `predictor.json`: the selected model, class order, feature version and temperature.
- `report.md`, `report.json`: results, limitations, coverage and feature importance.
- `test_predictions.parquet` / `.csv`: unmodified probabilities for error analysis.
- `forecasts/*.json`: probabilities for upcoming matches with the cutoff and generation dates.

The demonstration forecast file is replaced atomically. The persistent service saves real forecasts to PostgreSQL before matches start, reconciles results and serves ready probabilities through the API. For updating weights, running the service, permissions and the quality report, see the [prediction service guide](ONLINE.md). Heavy JOINs and training are not run when a match card is opened.
