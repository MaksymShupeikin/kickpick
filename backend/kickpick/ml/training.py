"""Bounded CPU training, temporal evaluation, calibration and portable artifacts."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from catboost import CatBoostClassifier
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.metrics import accuracy_score, confusion_matrix, log_loss
from sklearn.preprocessing import OneHotEncoder

from .features import CATEGORICAL, CLASS_NAMES, FEATURES, FEATURE_VERSION, model_frame, split_masks

SEED = 20261016


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def read_dataset(path):
    """Only accept a versioned, complete export made by the shared feature builder."""
    manifest = json.loads(path.with_name("manifest.json").read_text())
    if manifest["feature_version"] != FEATURE_VERSION:
        raise ValueError("Dataset feature version differs; export it again")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["features_sha256"]:
        raise ValueError("Dataset checksum differs from its export manifest")
    return pd.read_parquet(path), manifest


def calibrate(probabilities, temperature):
    return softmax(np.log(np.clip(probabilities, 1e-12, 1)) / temperature, axis=1)


def fit_temperature(probabilities, y):
    fit = minimize_scalar(lambda t: log_loss(y, calibrate(probabilities, t), labels=[0, 1, 2]),
                          bounds=(0.5, 3.0), method="bounded")
    if not fit.success:
        raise RuntimeError("Temperature calibration failed")
    return float(fit.x)


def metrics(y, probabilities):
    y = np.asarray(y, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    if p.shape != (len(y), 3) or not np.isfinite(p).all() or (p < 0).any():
        raise ValueError("Invalid H/D/A probabilities")
    if not np.allclose(p.sum(axis=1), 1, atol=1e-7):
        raise ValueError("Probabilities do not sum to one")
    chosen = p.argmax(axis=1)
    confidence = p.max(axis=1)
    bins = []
    for index in range(10):
        mask = (confidence >= index / 10) & (confidence < (index + 1) / 10 if index < 9 else confidence <= 1)
        if mask.any():
            bins.append({"from": index / 10, "to": (index + 1) / 10, "n": int(mask.sum()),
                         "confidence": float(confidence[mask].mean()),
                         "accuracy": float((chosen[mask] == y[mask]).mean())})
    return {
        "n": len(y), "log_loss": float(log_loss(y, p, labels=[0, 1, 2])),
        "brier_sum_3_classes": float(np.square(p - np.eye(3)[y]).sum(axis=1).mean()),
        "accuracy": float(accuracy_score(y, chosen)),
        "confidence_ece_10_bins": sum(b["n"] * abs(b["confidence"] - b["accuracy"]) for b in bins) / len(y),
        "calibration_bins": bins,
        "confusion_matrix_H_D_A": confusion_matrix(y, chosen, labels=[0, 1, 2]).tolist(),
    }


class Baseline:
    """Frequency, Elo logistic and independent Poisson. JSON, no pickle loading."""

    def __init__(self, state):
        self.state = state

    @staticmethod
    def _matrix(frame, categories, names):
        columns = [np.ones(len(frame))]
        for name in names:
            values = frame[name].astype(str).to_numpy()
            columns.extend((values == category).astype(float) for category in categories[name])
        return np.column_stack(columns)

    @classmethod
    def fit(cls, kind, frame):
        y = frame["target"].astype(int).to_numpy()
        if kind == "league_frequency":
            overall = (np.bincount(y, minlength=3) + 1) / (len(y) + 3)
            by_league = {}
            for league, group in frame.groupby("league"):
                counts = np.bincount(group["target"].astype(int), minlength=3)
                by_league[league] = ((counts + 20 * overall) / (len(group) + 20)).tolist()
            return cls({"kind": kind, "overall": overall.tolist(), "by_league": by_league})
        if kind == "elo_logistic":
            categories = {"league": sorted(frame["league"].unique().tolist())}
            x = cls._matrix(frame, categories, ["league"])
            x = np.column_stack([x, frame["elo_diff"].to_numpy() / 400])
            model = LogisticRegression(C=10, fit_intercept=False, max_iter=1000)
            model.fit(x, y)
            if model.classes_.tolist() != [0, 1, 2]:
                raise ValueError("Baseline training must contain all three outcomes")
            return cls({"kind": kind, "categories": categories, "coef": model.coef_.tolist()})
        if kind != "poisson":
            raise ValueError(f"Unknown baseline: {kind}")
        home, away = cls._goal_rows(frame)
        goals = pd.concat([home, away], ignore_index=True)
        names = ["league", "attack", "defense", "at_home"]
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        x = encoder.fit_transform(goals[names].astype(str))
        model = PoissonRegressor(alpha=0.02, max_iter=1000, tol=1e-7)
        model.fit(x, np.r_[frame["home_score"], frame["away_score"]].astype(float))
        categories = {name: values.tolist() for name, values in zip(names, encoder.categories_)}
        # The first coefficient multiplies an explicit intercept at prediction time.
        return cls({"kind": kind, "names": names, "categories": categories,
                    "coef": [float(model.intercept_), *model.coef_.tolist()]})

    @staticmethod
    def _goal_rows(frame):
        home = pd.DataFrame({"league": frame["league"].to_numpy(),
                             "attack": frame["home_team_id"].astype(str).to_numpy(),
                             "defense": frame["away_team_id"].astype(str).to_numpy(), "at_home": "1"})
        away = pd.DataFrame({"league": frame["league"].to_numpy(),
                             "attack": frame["away_team_id"].astype(str).to_numpy(),
                             "defense": frame["home_team_id"].astype(str).to_numpy(), "at_home": "0"})
        return home, away

    def predict_proba(self, frame):
        s = self.state
        if s["kind"] == "league_frequency":
            return np.asarray([s["by_league"].get(league, s["overall"]) for league in frame["league"]])
        if s["kind"] == "elo_logistic":
            x = self._matrix(frame, s["categories"], ["league"])
            x = np.column_stack([x, frame["elo_diff"].to_numpy() / 400])
            return softmax(x @ np.asarray(s["coef"]).T, axis=1)
        home, away = self._goal_rows(frame)
        rates = [np.exp(np.clip(self._matrix(rows, s["categories"], s["names"]) @ s["coef"], -4, 4))
                 for rows in (home, away)]
        # Skellam is the exact distribution of independent Poisson goal difference.
        from scipy.stats import skellam
        draw = skellam.pmf(0, *rates)
        away_win = skellam.cdf(-1, *rates)
        home_win = skellam.sf(0, *rates)
        p = np.column_stack([home_win, draw, away_win])
        return p / p.sum(axis=1, keepdims=True)


def train(dataset_path: Path, output: Path, threads=2):
    started = time.perf_counter()
    frame, manifest = read_dataset(dataset_path)
    masks = split_masks(frame)
    if any(int(mask.sum()) < 300 for mask in masks.values()):
        raise ValueError("Each temporal split needs at least 300 eligible matches")
    parts = {name: frame[mask].copy() for name, mask in masks.items()}
    x = {name: model_frame(part) for name, part in parts.items()}
    y = {name: part["target"].astype(int).to_numpy() for name, part in parts.items()}
    output.mkdir(parents=True, exist_ok=False)
    models, validation, timings = {}, {}, {}
    for kind in ("league_frequency", "elo_logistic", "poisson"):
        before = time.perf_counter()
        baseline = Baseline.fit(kind, parts["train"])
        models[kind] = baseline
        validation[kind] = metrics(y["validation"], baseline.predict_proba(parts["validation"]))
        write_json(output / f"{kind}.json", baseline.state)
        timings[kind] = time.perf_counter() - before
        print(f"{kind}: validation logloss={validation[kind]['log_loss']:.4f}", flush=True)
    candidates = []
    for years in (3, 6):
        fit_mask = parts["train"]["kickoff"] >= pd.Timestamp(f"{2023 - years}-07-01", tz="UTC")
        for depth in (4, 6):
            before = time.perf_counter()
            model = CatBoostClassifier(
                iterations=1400, depth=depth, learning_rate=0.035, l2_leaf_reg=8,
                loss_function="MultiClass", eval_metric="MultiClass", random_seed=SEED,
                thread_count=threads, allow_writing_files=False, verbose=False,
                cat_features=list(CATEGORICAL), early_stopping_rounds=100,
            )
            model.fit(x["train"][fit_mask], y["train"][fit_mask.to_numpy()],
                      eval_set=(x["validation"], y["validation"]), use_best_model=True)
            score = metrics(y["validation"], model.predict_proba(x["validation"]))
            candidate = {"years": years, "depth": depth, "trees": model.tree_count_,
                         "validation_log_loss": score["log_loss"],
                         "seconds": time.perf_counter() - before}
            candidates.append((candidate, model))
            print(f"catboost {years}y depth={depth}: validation logloss={score['log_loss']:.4f}, "
                  f"trees={model.tree_count_}", flush=True)
    best_settings, best_model = min(candidates, key=lambda item: item[0]["validation_log_loss"])
    models["catboost"] = best_model
    validation["catboost"] = metrics(y["validation"], best_model.predict_proba(x["validation"]))
    best_model.save_model(str(output / "catboost.cbm"))
    # Selection is completed before either calibration outcomes or test outcomes are read.
    champion = min(validation, key=lambda name: validation[name]["log_loss"])
    evaluations, temperatures, test_predictions = {}, {}, {}
    for name, model in models.items():
        probabilities = {part: np.asarray(model.predict_proba(x[part] if name == "catboost" else parts[part]))
                         for part in ("calibration", "test")}
        temperature = fit_temperature(probabilities["calibration"], y["calibration"])
        temperatures[name] = temperature
        calibrated = calibrate(probabilities["test"], temperature)
        test_predictions[name] = calibrated
        evaluations[name] = {
            "validation_raw": validation[name],
            "temperature": temperature,
            "test_raw": metrics(y["test"], probabilities["test"]),
            "test_calibrated": metrics(y["test"], calibrated),
            "test_by_league": {league: metrics(y["test"][mask], calibrated[mask])
                               for league in sorted(parts["test"]["league"].unique())
                               for mask in [(parts["test"]["league"] == league).to_numpy()]},
        }
    predictions = parts["test"][["match_id", "kickoff", "league", "home_team", "away_team", "target"]].copy()
    for name, probabilities in test_predictions.items():
        for index, label in enumerate(CLASS_NAMES):
            predictions[f"{name}_{label}"] = probabilities[:, index]
    predictions.to_parquet(output / "test_predictions.parquet", index=False)
    predictions.to_csv(output / "test_predictions.csv", index=False)
    dataset_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(), "feature_version": FEATURE_VERSION,
        "dataset_manifest": manifest,
        "dataset_sha256": dataset_hash, "class_order": list(CLASS_NAMES), "features": list(FEATURES),
        "categorical_features": list(CATEGORICAL), "seed": SEED, "threads": threads,
        "splits": {name: {"n": len(part), "first_kickoff": part["kickoff"].min().isoformat(),
                           "last_kickoff": part["kickoff"].max().isoformat()}
                   for name, part in parts.items()},
        "catboost_candidates": [candidate for candidate, _ in candidates],
        "catboost_selected": best_settings,
        "champion": champion, "selection": "Lowest raw validation log loss; test never used for selection",
        "temperatures": temperatures, "models": evaluations,
        "feature_importance": sorted(
            [{"feature": f, "importance": float(v)} for f, v in zip(FEATURES, best_model.feature_importances_)],
            key=lambda item: item["importance"], reverse=True),
        "total_seconds": time.perf_counter() - started,
        "limitations": [
            "The backtest is reconstructed from the current database. There are no historical snapshots; late corrections and rescheduled matches may distort data availability.",
            "Result availability is approximated as kickoff + 3 hours. Abandoned matches need real observed_at/finished_at values.",
            "Only five domestic leagues; each team needs at least five previous matches in that league.",
            "The cutoff is 24 hours before the match. Earlier test matches update the form and Elo of later matches; model weights stay fixed.",
            "No comparison with bookmaker odds, and no lineups, injuries, cup workload or historical transfers.",
            "Calibration is fitted on 2024/25, so its quality on that same season is not an independent check.",
            "Test was evaluated after parameter selection. If new models are tuned against this report, a new independent evaluation period is needed.",
            "This is the first experiment: weights were trained on data up to July 2023. Before publication, a refit using the chosen scheme and a prospective check are needed.",
        ],
    }
    add_diagnostics(report, predictions, frame)
    model_path = output / ("catboost.cbm" if champion == "catboost" else f"{champion}.json")
    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    report["model_version"] = f"{output.name}:{model_hash[:12]}"
    write_json(output / "report.json", report)
    write_json(output / "predictor.json", {
        "feature_version": FEATURE_VERSION, "features": list(FEATURES), "class_order": list(CLASS_NAMES),
        "champion": champion, "temperature": temperatures[champion], "dataset_sha256": dataset_hash,
        "horizon_hours": 24, "result_delay_hours": 3,
        "model_version": report["model_version"], "model_sha256": model_hash,
        "trained_through": parts["train"]["kickoff"].max().isoformat(),
        "calibrated_through": parts["calibration"]["kickoff"].max().isoformat(),
    })
    write_report(output / "report.md", report)
    print(f"Selected {champion}; artifacts: {output}; elapsed {report['total_seconds']:.1f}s", flush=True)
    return report


def add_diagnostics(report, predictions, frame):
    """Assess frozen predictions without refitting or changing model selection."""
    baseline = min((name for name in report["models"] if name != "catboost"),
                   key=lambda name: report["models"][name]["validation_raw"]["log_loss"])
    y = predictions["target"].astype(int).to_numpy()
    losses = {}
    for name in ("catboost", baseline):
        p = predictions[[f"{name}_{label}" for label in CLASS_NAMES]].to_numpy()
        losses[name] = -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))
    # Weekly clusters preserve some dependence between matches/teams in the same round.
    weeks = pd.to_datetime(predictions["kickoff"], utc=True).dt.tz_localize(None).dt.to_period("W-SUN")
    grouped = pd.DataFrame({"week": weeks, "delta": losses["catboost"] - losses[baseline]}).groupby("week")["delta"].agg(["sum", "count"])
    random = np.random.default_rng(SEED)
    sampled = random.integers(0, len(grouped), size=(2000, len(grouped)))
    boot = grouped["sum"].to_numpy()[sampled].sum(axis=1) / grouped["count"].to_numpy()[sampled].sum(axis=1)
    report["catboost_vs_best_baseline"] = {
        "baseline_selected_on_validation": baseline,
        "test_log_loss_delta_catboost_minus_baseline": float((losses["catboost"] - losses[baseline]).mean()),
        "weekly_cluster_bootstrap_95pct_interval": np.quantile(boot, [0.025, 0.975]).tolist(),
        "bootstrap_samples": 2000, "week_clusters": len(grouped),
        "interpretation": "A negative difference favours CatBoost. An interval that includes 0 does not confirm a robust advantage.",
    }
    dates = pd.to_datetime(frame["kickoff"], utc=True)
    eligible = (frame["home_history_games"] >= 5) & (frame["away_history_games"] >= 5)
    report["coverage"] = {}
    for name in report["splits"]:
        # Use whole July-to-July season periods, including teams excluded for short history.
        start = {"train": "2017-07-01", "validation": "2023-07-01",
                 "calibration": "2024-07-01", "test": "2025-07-01"}[name]
        end = {"train": "2023-07-01", "validation": "2024-07-01",
               "calibration": "2025-07-01", "test": "2026-07-01"}[name]
        mask = frame["target"].notna() & (dates >= pd.Timestamp(start, tz="UTC")) & (dates < pd.Timestamp(end, tz="UTC"))
        report["coverage"][name] = {"all_finished": int(mask.sum()), "eligible": int((mask & eligible).sum()),
                                    "excluded_short_history": int((mask & ~eligible).sum())}


def write_report(path, report):
    lines = ["# KickPick prediction experiment", "",
             "First experiment. Outcomes: H is a home win, D a draw, A an away win. Feature cutoff: 24 hours before kick-off.", "",
             "The model is selected on validation; calibration uses the following season; test is 2025/26.", "",
             "**Status:** Generated · **Scope:** first experiment, five domestic leagues", "",
             "| Split | Matches | First match | Last match |", "|---|---:|---|---|"]
    for name, split in report["splits"].items():
        lines.append(f"| {name} | {split['n']} | {split['first_kickoff'][:10]} | {split['last_kickoff'][:10]} |")
    lines.extend(["", "Lower LogLoss/Brier is better. Brier is the sum of squared errors over the three classes (0–2).", "",
                  "| Model | Validation LogLoss | Test LogLoss | Test Brier | Test accuracy |",
                  "|---|---:|---:|---:|---:|"])
    for name, model in report["models"].items():
        test = model["test_calibrated"]
        lines.append(f"| {name} | {model['validation_raw']['log_loss']:.4f} | {test['log_loss']:.4f} | "
                     f"{test['brier_sum_3_classes']:.4f} | {test['accuracy']:.1%} |")
    lines.extend(["", f"Selected on validation: **{report['champion']}**. Test probabilities are calibrated.", "",
                  f"Test coverage: {report['coverage']['test']['eligible']} of {report['coverage']['test']['all_finished']} matches; "
                  f"excluded for short history: {report['coverage']['test']['excluded_short_history']}.", ""])
    comparison = report["catboost_vs_best_baseline"]
    lower, upper = comparison["weekly_cluster_bootstrap_95pct_interval"]
    lines.extend([f"CatBoost vs {comparison['baseline_selected_on_validation']}: "
                  f"ΔLogLoss = {comparison['test_log_loss_delta_catboost_minus_baseline']:.4f}, "
                  f"95% interval by weekly blocks [{lower:.4f}; {upper:.4f}].", "",
                  comparison["interpretation"], "",
                  "## Limitations", "", *[f"- {item}" for item in report["limitations"]], "",
                  f"Training and evaluation: {report['total_seconds']:.1f} s, threads: {report['threads']}.",
                  f"Dataset SHA-256: `{report['dataset_sha256']}`.", ""])
    Path(path).write_text("\n".join(lines))


def forecast(dataset_path: Path, model_dir: Path, output: Path, as_of):
    meta = json.loads((model_dir / "predictor.json").read_text())
    if meta["feature_version"] != FEATURE_VERSION or meta["features"] != list(FEATURES):
        raise ValueError("Incompatible feature schema; retrain the model")
    if meta["class_order"] != list(CLASS_NAMES):
        raise ValueError("Incompatible outcome ordering")
    frame, manifest = read_dataset(dataset_path)
    as_of = pd.Timestamp(as_of)
    if as_of.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    age = as_of - pd.Timestamp(manifest["as_of"])
    if age < pd.Timedelta(0) or age > pd.Timedelta(hours=1):
        raise ValueError("Forecast needs a snapshot from the preceding hour; run export again")
    eligible = (frame["status"] == "NS") & (frame["kickoff"] > as_of) & (
        frame["kickoff"] <= as_of + pd.Timedelta(hours=24)) & (frame["prediction_time"] <= as_of) & (
        frame["home_history_games"] >= 5) & (frame["away_history_games"] >= 5)
    selected = frame[eligible].copy()
    columns = ["match_id", "kickoff", "prediction_time", "league", "home_team", "away_team"]
    result = selected[columns].copy()
    name = meta["champion"]
    model_path = model_dir / ("catboost.cbm" if name == "catboost" else f"{name}.json")
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != meta["model_sha256"]:
        raise ValueError("Model checksum differs from its predictor manifest")
    if len(selected):
        if name == "catboost":
            model = CatBoostClassifier(thread_count=2)
            model.load_model(str(model_dir / "catboost.cbm"))
            raw = model.predict_proba(model_frame(selected), thread_count=2)
        else:
            raw = Baseline(json.loads((model_dir / f"{name}.json").read_text())).predict_proba(selected)
        probabilities = calibrate(raw, meta["temperature"])
        for index, label in enumerate(CLASS_NAMES):
            result[f"p_{label}"] = probabilities[:, index]
    else:
        for label in CLASS_NAMES:
            result[f"p_{label}"] = pd.Series(dtype=float)
    result["generated_at"] = as_of
    result["source_as_of"] = pd.Timestamp(manifest["as_of"])
    result["feature_version"] = FEATURE_VERSION
    result["model"] = name
    result["model_version"] = meta["model_version"]
    # Atomic publication: API integrations must never see a half-written prediction file.
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    result.to_json(temporary, orient="records", date_format="iso", indent=2)
    temporary.replace(output)
    print(f"Wrote {len(result)} upcoming forecasts to {output}", flush=True)
    return result
