"""Refresh a frozen experiment recipe; quality must be measured prospectively."""
from datetime import datetime, timezone
import hashlib
import json
import time

from catboost import CatBoostClassifier
import pandas as pd

from .bundle import BASELINES
from .features import CATEGORICAL, CLASS_NAMES, FEATURES, FEATURE_VERSION, LEAGUES, model_frame
from .training import Baseline, SEED, fit_temperature, read_dataset, write_json


def refit(dataset, template, output, *, threads=2):
    started = time.perf_counter()
    frame, manifest = read_dataset(dataset)
    recipe = json.loads(template.read_text())
    if recipe["feature_version"] != FEATURE_VERSION or recipe["features"] != list(FEATURES):
        raise ValueError("Recipe feature schema differs")
    champion, settings = recipe["champion"], recipe["catboost_selected"]
    as_of = pd.Timestamp(manifest["as_of"])
    calibration_start = (as_of - pd.Timedelta(days=180)).normalize()
    # Purge the forecast horizon and result delay from the training/calibration border.
    train_cutoff = calibration_start - pd.Timedelta(hours=24)
    train_start = train_cutoff - pd.DateOffset(years=int(settings["years"]))
    eligible = frame["target"].notna() & (frame["home_history_games"] >= 5) & (frame["away_history_games"] >= 5)
    train = frame[eligible & (frame["kickoff"] >= train_start)
                  & (frame["kickoff"] + pd.Timedelta(hours=3) < train_cutoff)].copy()
    calibration = frame[eligible & (frame["kickoff"] >= calibration_start)
                        & (frame["kickoff"] + pd.Timedelta(hours=3) < as_of)].copy()
    if len(train) < 3000 or len(calibration) < 300:
        raise ValueError("Refit requires at least 3000 train and 300 calibration matches")
    output.mkdir(parents=True, exist_ok=False)
    temperatures = {}
    for name in BASELINES:
        model = Baseline.fit(name, train)
        temperatures[name] = fit_temperature(model.predict_proba(calibration), calibration["target"].astype(int))
        write_json(output / f"{name}.json", model.state)
    model = CatBoostClassifier(
        iterations=int(settings["trees"]), depth=int(settings["depth"]), learning_rate=0.035, l2_leaf_reg=8,
        loss_function="MultiClass", random_seed=SEED, thread_count=threads,
        allow_writing_files=False, verbose=False, cat_features=list(CATEGORICAL),
    )
    model.fit(model_frame(train), train["target"].astype(int))
    model.save_model(str(output / "catboost.cbm"))
    temperatures["catboost"] = fit_temperature(model.predict_proba(model_frame(calibration)), calibration["target"].astype(int))
    model_path = output / ("catboost.cbm" if champion == "catboost" else f"{champion}.json")
    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    metadata = {
        "feature_version": FEATURE_VERSION, "features": list(FEATURES), "class_order": list(CLASS_NAMES),
        "leagues": list(LEAGUES), "champion": champion, "temperature": temperatures[champion],
        "temperatures": temperatures, "dataset_sha256": manifest["features_sha256"],
        "horizon_hours": 24, "result_delay_hours": 3,
        "model_version": f"{output.name}:{model_hash[:12]}", "model_sha256": model_hash,
        "trained_through": train["kickoff"].max().isoformat(),
        "calibrated_through": calibration["kickoff"].max().isoformat(),
        "evaluation_status": "awaiting_prospective_results",
    }
    write_json(output / "predictor.json", metadata)
    write_json(output / "refit.json", {
        "created_at": datetime.now(timezone.utc).isoformat(), "source_as_of": as_of.isoformat(),
        "template_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
        "frozen_parameters": settings, "champion_fixed_from_template": champion,
        "train": {"n": len(train), "from": train["kickoff"].min().isoformat(), "to": train["kickoff"].max().isoformat()},
        "calibration": {"n": len(calibration), "from": calibration["kickoff"].min().isoformat(),
                        "to": calibration["kickoff"].max().isoformat()},
        "seconds": time.perf_counter() - started,
        "warning": "No independent quality score for these refreshed weights. Evaluate actual future forecasts; old test scores do not apply.",
        "dataset_manifest": manifest,
    })
    print(f"Refitted {champion}: train={len(train)}, calibration={len(calibration)}, "
          f"{time.perf_counter()-started:.1f}s; prospective evaluation pending", flush=True)
