from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.main import create_app  # noqa: E402
from app.ml.model import QoEModel  # noqa: E402


def test_model_prefers_safe_quality_under_low_bandwidth():
    model = QoEModel()
    low = model.recommend(1.2, 1.0, 80)
    high = model.recommend(12.0, 12.0, 30)
    assert low.bitrate_mbps < high.bitrate_mbps
    assert low.risk <= 0.35


def test_telemetry_is_idempotent_and_summary_is_computed(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'cinescaler.db'}")
    client = TestClient(app)
    created = client.post("/api/v1/sessions", json={"title": "Launch trailer", "device": "browser"})
    session_id = created.json()["id"]
    event = {"event_id": "event-0001", "throughput_mbps": 6, "buffer_seconds": 7, "latency_ms": 40, "bitrate_mbps": 3, "rebuffered": False}
    first = client.post(f"/api/v1/sessions/{session_id}/telemetry", json={"events": [event]})
    second = client.post(f"/api/v1/sessions/{session_id}/telemetry", json={"events": [event]})
    assert first.json()["accepted"] == 1
    assert second.json()["duplicates_ignored"] == 1
    summary = client.get("/api/v1/analytics/summary").json()
    assert summary["events"] == 1
    recommendation = client.get(f"/api/v1/sessions/{session_id}/recommendation", params={"throughput_mbps": 6, "buffer_seconds": 7, "latency_ms": 40})
    assert recommendation.status_code == 200
    assert "rationale" in recommendation.json()


def test_model_retraining_is_evaluated_versioned_and_restored(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'model-registry.db'}"
    app = create_app(database_url)
    client = TestClient(app)
    created = client.post("/api/v1/sessions", json={"title": "Training stream", "device": "simulator"})
    session_id = created.json()["id"]
    for index, rebuffered in enumerate([False, False, True, False, True, False]):
        event = {"event_id": f"training-{index}", "throughput_mbps": 2 + index, "buffer_seconds": 2 + index, "latency_ms": 35, "bitrate_mbps": 3, "rebuffered": rebuffered}
        response = client.post(f"/api/v1/sessions/{session_id}/telemetry", json={"events": [event]})
        assert response.status_code == 200

    before = client.get("/api/v1/model/status").json()
    retrained = client.post("/api/v1/model/retrain")
    assert retrained.status_code == 200
    body = retrained.json()
    assert body["version"] == before["version"] + 1
    assert body["training_samples"] == 5
    assert body["evaluation_samples"] == 1
    assert set(body["metrics"]) == {"samples", "accuracy", "precision", "recall", "brier_score"}

    restarted = create_app(database_url)
    restored = TestClient(restarted).get("/api/v1/model/status").json()
    assert restored["version"] == body["version"]
    assert restored["trained_samples"] == body["trained_samples"]
