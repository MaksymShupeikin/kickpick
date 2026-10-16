"""A model bundle and its frozen comparison baselines."""
import hashlib
import json

from catboost import CatBoostClassifier
import numpy as np

from .features import CLASS_NAMES, FEATURES, FEATURE_VERSION, model_frame
from .training import Baseline, calibrate

BASELINES = ("league_frequency", "elo_logistic", "poisson")


class ModelBundle:
    def __init__(self, directory):
        self.metadata = json.loads((directory / "predictor.json").read_text())
        meta = self.metadata
        if meta["features"] != list(FEATURES) or meta["feature_version"] != FEATURE_VERSION or meta["class_order"] != list(CLASS_NAMES):
            raise ValueError("Model bundle feature/class schema mismatch")
        self.champion = meta["champion"]
        self.models, self.temperatures, hashes = {}, {}, {}
        for name in (*BASELINES, "catboost"):
            file = directory / ("catboost.cbm" if name == "catboost" else f"{name}.json")
            hashes[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
            if name == "catboost":
                model = CatBoostClassifier()
                model.load_model(str(file))
                if model.classes_.tolist() != [0, 1, 2]:
                    raise ValueError("CatBoost class order mismatch")
            else:
                model = Baseline(json.loads(file.read_text()))
            self.models[name] = model
        champion_file = "catboost.cbm" if self.champion == "catboost" else f"{self.champion}.json"
        if hashes[champion_file] != meta["model_sha256"]:
            raise ValueError("Model checksum differs from predictor manifest")
        # Old experiment bundles keep all temperatures in their evaluation report.
        temperatures = meta.get("temperatures")
        if temperatures is None:
            temperatures = json.loads((directory / "report.json").read_text())["temperatures"]
        for name in self.models:
            temperature = float(temperatures[name])
            if not np.isfinite(temperature) or not 0.5 <= temperature <= 3:
                raise ValueError("Invalid bundle temperature")
            self.temperatures[name] = temperature
        identity = {"metadata": meta, "hashes": hashes, "temperatures": self.temperatures}
        self.sha256 = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()
        self.version = f"{meta['model_version']}:{self.sha256[:12]}"
        self.registry_metadata = identity | {"class_order": list(CLASS_NAMES), "champion": self.champion}

    def predict_all(self, frame):
        x = model_frame(frame)
        results = {}
        for name, model in self.models.items():
            raw = model.predict_proba(x, thread_count=2) if name == "catboost" else model.predict_proba(frame)
            p = calibrate(raw, self.temperatures[name])
            if not np.isfinite(p).all() or (p < 0).any() or not np.allclose(p.sum(axis=1), 1, atol=1e-8):
                raise ValueError(f"Invalid probabilities from {name}")
            results[name] = p
        return results
