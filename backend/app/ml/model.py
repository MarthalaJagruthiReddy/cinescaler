from __future__ import annotations

import math
from dataclasses import dataclass


BITRATES = (0.8, 1.5, 3.0, 5.0, 8.0)


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(min(value, 30), -30)))


@dataclass
class Prediction:
    bitrate_mbps: float
    risk: float


class QoEModel:
    """Tiny online logistic model for demonstrating an explainable ABR policy."""

    def __init__(self):
        # Intercept, demand ratio, low-buffer pressure, and normalized latency.
        self.weights = [-3.7, 2.9, 0.75, 0.18]
        self.learning_rate = 0.04

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

    def retrain(self, samples: list[dict], epochs: int = 3) -> None:
        for _ in range(epochs):
            for sample in samples:
                self.update(**sample)
