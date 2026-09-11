from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
REQUESTS = int(os.getenv("REQUESTS", "250"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "20"))


def request_json(method: str, path: str, payload: dict | None = None) -> tuple[int, float]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(f"{BASE_URL}{path}", data=body, method=method, headers={"content-type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
            return response.status, (time.perf_counter() - started) * 1000
    except Exception:
        return 0, (time.perf_counter() - started) * 1000


def request_json_body(method: str, path: str, payload: dict | None = None) -> tuple[int, float, dict]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(f"{BASE_URL}{path}", data=body, method=method, headers={"content-type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, (time.perf_counter() - started) * 1000, json.loads(response.read())
    except Exception:
        return 0, (time.perf_counter() - started) * 1000, {}


def percentile(values: list[float], value: int) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, (value * len(ordered) + 99) // 100 - 1))
    return round(ordered[index], 2)


def summarize(name: str, endpoint: str, samples: list[tuple[int, float]], elapsed: float) -> dict:
    successful = [sample for sample in samples if sample[0] == 200]
    latencies = [sample[1] for sample in successful]
    return {
        "benchmark": name,
        "requests": len(samples),
        "concurrency": CONCURRENCY,
        "endpoint": endpoint,
        "successful_requests": len(successful),
        "errors": len(samples) - len(successful),
        "request_throughput_per_second": round(len(successful) / elapsed, 2),
        "latency_ms": {"p50": percentile(latencies, 50), "p95": percentile(latencies, 95), "p99": percentile(latencies, 99)},
    }


def main() -> None:
    status, _, session = request_json_body("POST", "/api/v1/sessions", {"title": "Load test stream", "device": "benchmark-client"})
    if status != 201:
        raise SystemExit(f"session seed failed with HTTP {status}")
    session_id = session["id"]

    def telemetry(index: int) -> tuple[int, float]:
        event = {
            "event_id": f"load-test-{index}",
            "throughput_mbps": 8,
            "buffer_seconds": 10,
            "latency_ms": 35,
            "bitrate_mbps": 5,
            "rebuffered": False,
        }
        return request_json("POST", f"/api/v1/sessions/{session_id}/telemetry", {"events": [event]})

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        telemetry_samples = list(executor.map(telemetry, range(REQUESTS)))
    telemetry_elapsed = time.perf_counter() - started

    def recommendation(_: int) -> tuple[int, float]:
        query = urllib.parse.urlencode({"throughput_mbps": 8, "buffer_seconds": 10, "latency_ms": 35})
        return request_json("GET", f"/api/v1/sessions/{session_id}/recommendation?{query}")

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        recommendation_samples = list(executor.map(recommendation, range(REQUESTS)))
    recommendation_elapsed = time.perf_counter() - started

    result = {
        "benchmark": "CineScaler API load test",
        "telemetry": summarize("CineScaler telemetry ingestion", f"POST /api/v1/sessions/{session_id}/telemetry", telemetry_samples, telemetry_elapsed),
        "recommendation": summarize("CineScaler recommendations", "GET /api/v1/sessions/:id/recommendation", recommendation_samples, recommendation_elapsed),
        "database": "PostgreSQL",
    }
    print(json.dumps(result, indent=2))
    if result["telemetry"]["errors"] or result["recommendation"]["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
