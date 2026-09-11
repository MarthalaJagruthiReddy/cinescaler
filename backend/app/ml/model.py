from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime


BITRATES = (0.8, 1.5, 3.0, 5.0, 8.0)


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(min(value, 30), -30)))


@dataclass
class Prediction:
    bitrate_mbps: float
    risk: float


class QoEModel:
    """Explainable online QoE model with versioned evaluation metadata."""

    def __init__(self):
        # Intercept, demand ratio, low-buffer pressure, and normalized latency.
        self.weights = [-3.7, 2.9, 0.75, 0.18]
        self.learning_rate = 0.04
        self.version = 1
        self.trained_samples = 0
        self.last_metrics: dict[str, float] = {
            "samples": 0,
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "brier_score": 0.0,
        }
        self.last_trained_at: datetime | None = None

    @staticmethod
    def features(throughput_mbps: float, buffer_seconds: float, latency_ms: float, bitrate_mbps: float) -> list[float]:
        demand_ratio = bitrate_mbps / max(throughput_mbps, 0.1)
        low_buffer_pressure = 1.0 / (buffer_seconds + 1.0)
        normalized_latency = latency_ms / 100.0
        return [1.0, demand_ratio, low_buffer_pressure, normalized_latency]

    def predict_risk(self, throughput_mbps: float, buffer_seconds: float, latency_ms: float, bitrate_mbps: float) -> float:
        values = self.features(throughput_mbps, buffer_seconds, latency_ms, bitrate_mbps)
        return sigmoid(sum(weight * value for weight, value in zip(self.weights, values, strict=True)))

    def recommend(self, throughput_mbps: float, buffer_seconds: float, latency_ms: float) -> Prediction:
        predictions = [Prediction(rate, self.predict_risk(throughput_mbps, buffer_seconds, latency_ms, rate)) for rate in BITRATES]
        safe = [prediction for prediction in predictions if prediction.risk <= 0.35]
        return max(safe or predictions[:1], key=lambda prediction: prediction.bitrate_mbps)

    def update(self, throughput_mbps: float, buffer_seconds: float, latency_ms: float, bitrate_mbps: float, rebuffered: bool) -> float:
        values = self.features(throughput_mbps, buffer_seconds, latency_ms, bitrate_mbps)
        prediction = sigmoid(sum(weight * value for weight, value in zip(self.weights, values, strict=True)))
        target = 1.0 if rebuffered else 0.0
        error = prediction - target
        self.weights = [weight - self.learning_rate * error * value for weight, value in zip(self.weights, values, strict=True)]
        return prediction

    def clone(self) -> "QoEModel":
        candidate = QoEModel()
        candidate.weights = deepcopy(self.weights)
        candidate.learning_rate = self.learning_rate
        candidate.version = self.version
        candidate.trained_samples = self.trained_samples
        candidate.last_metrics = deepcopy(self.last_metrics)
        candidate.last_trained_at = self.last_trained_at
        return candidate

    def evaluate(self, samples: list[dict]) -> dict[str, float]:
        if not samples:
            return {"samples": 0, "accuracy": 0.0, "precision": 0.0, "recall": 0.0, "brier_score": 0.0}
        predictions = []
        for sample in samples:
            risk = self.predict_risk(sample["throughput_mbps"], sample["buffer_seconds"], sample["latency_ms"], sample["bitrate_mbps"])
            target = 1 if sample["rebuffered"] else 0
            predictions.append((risk, target))
        true_positive = sum(risk >= 0.5 and target == 1 for risk, target in predictions)
        predicted_positive = sum(risk >= 0.5 for risk, _ in predictions)
        actual_positive = sum(target == 1 for _, target in predictions)
        correct = sum((risk >= 0.5) == bool(target) for risk, target in predictions)
        return {
            "samples": len(samples),
            "accuracy": round(correct / len(samples), 4),
            "precision": round(true_positive / predicted_positive, 4) if predicted_positive else 0.0,
            "recall": round(true_positive / actual_positive, 4) if actual_positive else 0.0,
            "brier_score": round(sum((risk - target) ** 2 for risk, target in predictions) / len(samples), 4),
        }

    def status(self) -> dict:
        return {
            "version": self.version,
            "trained_samples": self.trained_samples,
            "metrics": self.last_metrics,
            "last_trained_at": self.last_trained_at,
        }

    def restore(self, version: int, weights: list[float], trained_samples: int, metrics: dict[str, float], trained_at: datetime | None) -> None:
        self.version = version
        self.weights = list(weights)
        self.trained_samples = trained_samples
        self.last_metrics = dict(metrics)
        self.last_trained_at = trained_at

    def retrain(self, samples: list[dict], epochs: int = 3) -> None:
        for _ in range(epochs):
            for sample in samples:
                self.update(**sample)
