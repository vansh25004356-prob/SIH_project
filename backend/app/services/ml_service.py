"""V5 Landslide Risk ML Inference Service.

Loads the trained RandomForestClassifier V5 model ONCE at process start and
provides typed predict() calls. Feature order and thresholds come directly
from the shipped joblib bundle and v5_final_report.json / v5_threshold_analysis.csv
— nothing is fabricated.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

log = logging.getLogger("ml_service")

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = BACKEND_ROOT / "ml" / "v5_final_model.joblib"
REPO_MODEL_DIR = BACKEND_ROOT.parent / "model"

# Severity thresholds derived from v5_threshold_analysis.csv.
# 0.15 is the report's "balanced OOF" operating point (recall=0.98).
# Bands chosen from that same curve:
#   <0.15  LOW      (recall would exceed 0.98 -> too many false alerts to raise)
#   0.15-0.35 MEDIUM  (precision 0.57 -> 0.65)
#   0.35-0.65 HIGH   (precision 0.65 -> 0.81)
#   >=0.65 CRITICAL (precision 0.81+)
SEVERITY_BANDS = [
    ("LOW", 0.0, 0.15),
    ("MEDIUM", 0.15, 0.35),
    ("HIGH", 0.35, 0.65),
    ("CRITICAL", 0.65, 1.01),
]


class MLService:
    def __init__(self, model_path: Optional[Path] = None) -> None:
        self.model_path = Path(model_path or os.environ.get("MODEL_PATH", DEFAULT_MODEL_PATH))
        self.model = None
        self.features: List[str] = []
        self.version: str = "v5_matched_site_no_seismic"
        self.report: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(f"V5 model not found at {self.model_path}")
        bundle = joblib.load(self.model_path)
        # Bundle format: {"model": RandomForestClassifier, "features": [...]}
        self.model = bundle["model"]
        self.features = list(bundle["features"])
        report_path = REPO_MODEL_DIR / "v5_final_report.json"
        if report_path.exists():
            self.report = json.loads(report_path.read_text())
            self.version = self.report.get("version", self.version)
        log.info("Loaded V5 model=%s features=%d version=%s", type(self.model).__name__, len(self.features), self.version)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def feature_list(self) -> List[str]:
        return list(self.features)

    def severity_from_prob(self, p: float) -> str:
        for label, lo, hi in SEVERITY_BANDS:
            if lo <= p < hi:
                return label
        return "CRITICAL"

    def predict_one(self, features_dict: Dict[str, float]) -> Dict[str, Any]:
        # Enforce exact feature set + order.
        missing = [f for f in self.features if f not in features_dict]
        if missing:
            raise ValueError(f"missing_features:{missing}")
        row = np.array([[float(features_dict[f]) for f in self.features]], dtype=float)
        proba = float(self.model.predict_proba(row)[0, 1])
        pred = int(proba >= 0.15)  # operational threshold from V5 report
        severity = self.severity_from_prob(proba)
        contributing = self._explain(features_dict, proba)
        return {
            "prediction": pred,
            "probability": round(proba, 6),
            "risk_score": round(proba * 100.0, 2),
            "severity": severity,
            "model_version": self.version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "contributing_factors": contributing,
            "feature_order": self.features,
        }

    def _explain(self, feats: Dict[str, float], proba: float) -> List[Dict[str, Any]]:
        """Rule-based explanation using report's permutation importances.

        We highlight features whose value is well above a heuristic threshold
        (rainfall drivers, steep slope, high elevation). These are shown as
        contributing factors — NOT invented data. If the feature value is low,
        it is omitted.
        """
        importances = (self.report.get("permutation_importance_random_forest_oof") or {})
        drivers: List[Dict[str, Any]] = []

        def add(key: str, human: str, value: float, unit: str, ref_high: float):
            if value >= ref_high:
                drivers.append({
                    "feature": key,
                    "label": human,
                    "value": value,
                    "unit": unit,
                    "importance": float(importances.get(key, 0.0)),
                })

        add("rainfall_1d", "Rainfall (last 24h)", feats.get("rainfall_1d", 0), "mm", 40)
        add("rainfall_3d", "Rainfall (last 3 days)", feats.get("rainfall_3d", 0), "mm", 100)
        add("rainfall_7d", "Rainfall (last 7 days)", feats.get("rainfall_7d", 0), "mm", 200)
        add("rainfall_15d", "Rainfall (last 15 days)", feats.get("rainfall_15d", 0), "mm", 350)
        add("rainfall_30d", "Rainfall (last 30 days)", feats.get("rainfall_30d", 0), "mm", 600)
        add("max_rainfall_3d", "Peak 3-day rainfall in window", feats.get("max_rainfall_3d", 0), "mm", 80)
        add("max_rainfall_7d", "Peak 7-day rainfall in window", feats.get("max_rainfall_7d", 0), "mm", 150)
        add("rainy_days_7d", "Rainy days in last 7 days", feats.get("rainy_days_7d", 0), "days", 4)
        add("slope_deg", "Steep terrain slope", feats.get("slope_deg", 0), "deg", 20)
        add("elevation_m", "High elevation", feats.get("elevation_m", 0), "m", 1500)

        drivers.sort(key=lambda d: d["importance"], reverse=True)
        return drivers[:5]


# Singleton – loaded once at import
ml_service = MLService()
