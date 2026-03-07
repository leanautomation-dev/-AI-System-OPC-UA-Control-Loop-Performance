"""
AI Engine  –  Anomaly detection, CLPM scoring, and predictive alarm generation.
"""
from __future__ import annotations
import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

import numpy as np
import yaml
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

log = logging.getLogger(__name__)

with open("config.yaml") as f:
    CFG = yaml.safe_load(f)

AI_CFG = CFG["ai"]
CLPM_CFG = AI_CFG["clpm_scoring"]


# ─────────────────────────────────────────────────────────────────────────────
# CLPM Performance Scoring
# ─────────────────────────────────────────────────────────────────────────────
def compute_clpm_score(
    pv_arr: np.ndarray,
    sp_arr: np.ndarray,
    co_arr: np.ndarray,
) -> dict:
    """
    Compute IAE-based CLPM performance score in [0, 1].
    Mirrors the metrics in clpm_metrics.csv.
    """
    if len(pv_arr) < 2:
        return {"score": None, "grade": "Unknown"}

    error = pv_arr - sp_arr
    dt = 1.0  # assume 1-second samples unless told otherwise

    iae = float(np.sum(np.abs(error)) * dt)
    aae = float(np.mean(np.abs(error)))
    pv_std = float(np.std(pv_arr))
    co_travel = float(np.sum(np.abs(np.diff(co_arr))))
    sp_range = float(np.ptp(sp_arr)) if np.ptp(sp_arr) > 0 else 1.0

    # Normalised error index (0 = perfect, 1 = terrible)
    nei = min(aae / sp_range, 1.0)
    score = round(1.0 - nei, 4)

    # Oscillation detection via zero-crossings of error
    sign_changes = np.where(np.diff(np.sign(error)))[0]
    oscillation_index = len(sign_changes)

    if score >= CLPM_CFG["good_threshold"]:
        grade = "Good"
    elif score >= CLPM_CFG["acceptable_threshold"]:
        grade = "Acceptable"
    elif score >= CLPM_CFG["poor_threshold"]:
        grade = "Poor"
    else:
        grade = "Bad"

    return {
        "score": score,
        "grade": grade,
        "iae": round(iae, 2),
        "aae": round(aae, 4),
        "pv_std": round(pv_std, 4),
        "co_travel": round(co_travel, 4),
        "oscillation_index": oscillation_index,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Anomaly Detection
# ─────────────────────────────────────────────────────────────────────────────
class AnomalyDetector:
    def __init__(self, controller: str):
        self.controller = controller
        self.window_size = AI_CFG["anomaly_detection"]["window_size"]
        self.contamination = AI_CFG["anomaly_detection"]["contamination"]
        self._pv: deque[float] = deque(maxlen=self.window_size)
        self._sp: deque[float] = deque(maxlen=self.window_size)
        self._co: deque[float] = deque(maxlen=self.window_size)
        self._model: IsolationForest | None = None
        self._scaler = StandardScaler()
        self._trained = False
        self._retrain_counter = 0

    def update(self, pv: float, sp: float, co: float):
        self._pv.append(pv)
        self._sp.append(sp)
        self._co.append(co)
        self._retrain_counter += 1

        if (
            len(self._pv) == self.window_size
            and self._retrain_counter >= AI_CFG["anomaly_detection"]["retrain_interval"] // 60
        ):
            self._train()
            self._retrain_counter = 0

    def _train(self):
        X = np.column_stack([self._pv, self._sp, self._co])
        X_scaled = self._scaler.fit_transform(X)
        self._model = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100,
        )
        self._model.fit(X_scaled)
        self._trained = True

    def score_point(self, pv: float, sp: float, co: float) -> dict:
        if not self._trained or self._model is None:
            return {"anomaly": False, "score": 0.0, "reason": "model_not_ready"}

        X = self._scaler.transform([[pv, sp, co]])
        pred = self._model.predict(X)[0]
        raw_score = float(self._model.score_samples(X)[0])
        is_anomaly = int(pred) == -1

        reason = None
        if is_anomaly:
            # Simple rule-based reason attribution
            pv_arr = np.array(self._pv)
            sp_arr = np.array(self._sp)
            deviation = abs(pv - sp)
            mean_dev = float(np.mean(np.abs(pv_arr - sp_arr)))
            if deviation > 3 * mean_dev:
                reason = "high_deviation"
            elif abs(pv - np.mean(pv_arr)) > 3 * np.std(pv_arr):
                reason = "pv_spike"
            elif abs(co - np.mean(list(self._co))) > 2 * np.std(list(self._co)):
                reason = "co_saturation"
            else:
                reason = "multivariate_anomaly"

        return {
            "anomaly": is_anomaly,
            "score": round(raw_score, 4),
            "reason": reason,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Alarm Predictor  –  simple threshold lookahead
# ─────────────────────────────────────────────────────────────────────────────
class AlarmPredictor:
    def __init__(self, controller: str):
        self.controller = controller
        self.lookahead = AI_CFG["alarm_prediction"]["lookahead_minutes"]
        self._errors: deque[float] = deque(maxlen=120)

    def update(self, error: float):
        self._errors.append(abs(error))

    def predict(self, sp: float) -> dict:
        if len(self._errors) < 10:
            return {"predicted_alarm": False, "confidence": 0.0}

        trend = np.polyfit(range(len(self._errors)), self._errors, 1)[0]
        if trend <= 0:
            return {"predicted_alarm": False, "confidence": 0.0}

        current_error = self._errors[-1]
        projected_error = current_error + trend * self.lookahead * 60
        alarm_threshold = abs(sp) * 0.2  # 20% of SP is "alarm"

        if projected_error > alarm_threshold:
            confidence = min(
                1.0,
                projected_error / alarm_threshold * 0.8,
            )
            return {
                "predicted_alarm": True,
                "confidence": round(confidence, 3),
                "projected_error": round(projected_error, 4),
                "minutes_ahead": self.lookahead,
            }
        return {"predicted_alarm": False, "confidence": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# AI Manager – one per process
# ─────────────────────────────────────────────────────────────────────────────
class AIManager:
    def __init__(self):
        self._detectors: dict[str, AnomalyDetector] = {}
        self._predictors: dict[str, AlarmPredictor] = {}
        self._pv_buffers: dict[str, deque] = defaultdict(lambda: deque(maxlen=300))
        self._sp_buffers: dict[str, deque] = defaultdict(lambda: deque(maxlen=300))
        self._co_buffers: dict[str, deque] = defaultdict(lambda: deque(maxlen=300))

    def ingest(self, records: list[dict]) -> list[dict]:
        """Process a batch of tag records; return AI enriched insights."""
        # Group by controller
        by_ctrl: dict[str, dict[str, float]] = defaultdict(dict)
        for r in records:
            ctrl = r.get("controller")
            signal = r.get("signal")
            val = r.get("value")
            if ctrl and signal and val is not None:
                by_ctrl[ctrl][signal] = float(val)

        insights = []
        for ctrl, signals in by_ctrl.items():
            pv = signals.get("PV")
            sp = signals.get("SP")
            co = signals.get("CO")
            if pv is None or sp is None or co is None:
                continue

            # Ensure detector/predictor exist
            if ctrl not in self._detectors:
                self._detectors[ctrl] = AnomalyDetector(ctrl)
                self._predictors[ctrl] = AlarmPredictor(ctrl)

            det = self._detectors[ctrl]
            pred = self._predictors[ctrl]

            det.update(pv, sp, co)
            pred.update(pv - sp)

            self._pv_buffers[ctrl].append(pv)
            self._sp_buffers[ctrl].append(sp)
            self._co_buffers[ctrl].append(co)

            anomaly_result = det.score_point(pv, sp, co)
            pred_result = pred.predict(sp)

            # Compute rolling CLPM score (last 60 points)
            pv_arr = np.array(self._pv_buffers[ctrl])
            sp_arr = np.array(self._sp_buffers[ctrl])
            co_arr = np.array(self._co_buffers[ctrl])
            clpm = compute_clpm_score(pv_arr, sp_arr, co_arr)

            insights.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "controller": ctrl,
                "pv": pv,
                "sp": sp,
                "co": co,
                "anomaly": anomaly_result,
                "alarm_prediction": pred_result,
                "clpm": clpm,
            })

        return insights


# Singleton instance
ai_manager = AIManager()
