from pathlib import Path
import os
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.main import create_app  # noqa: E402


@pytest.mark.skipif(os.getenv("CINESCALER_INTEGRATION") != "1", reason="requires the PostgreSQL integration environment")
def test_postgres_api_round_trip():
    client = TestClient(create_app(os.environ["DATABASE_URL"]))
    created = client.post("/api/v1/sessions", json={"title": f"Integration {uuid4()}", "device": "ci"})
    assert created.status_code == 201
    session_id = created.json()["id"]

    event = {
        "event_id": f"integration-{uuid4()}",
        "throughput_mbps": 8,
        "buffer_seconds": 10,
        "latency_ms": 35,
        "bitrate_mbps": 5,
        "rebuffered": False,
    }
    response = client.post(f"/api/v1/sessions/{session_id}/telemetry", json={"events": [event]})
    assert response.status_code == 200
    assert response.json()["accepted"] == 1

    summary = client.get("/api/v1/analytics/summary")
    assert summary.status_code == 200
    assert summary.json()["events"] >= 1
