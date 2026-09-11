# CineScaler

CineScaler is a telemetry-driven adaptive streaming service. A playback client sends throughput, buffer, latency, bitrate, and rebuffer events; an online QoE model learns from those observations and recommends the highest quality profile below a predicted rebuffer-risk threshold.

## Architecture

```mermaid
flowchart TD
    Player["Playback client"] --> API["FastAPI service"]
    API --> DB["PostgreSQL sessions and telemetry"]
    API --> Model["Online QoE model and bitrate policy"]
    API --> WS["WebSocket dashboard stream"]
    UI["React dashboard"] --> API
```

The model is intentionally small and explainable: features, weights, risk, and the final bitrate decision are inspectable. The service is designed as an experimentation platform rather than a replacement for a production-scale commercial ABR stack.

## Features

- Batch telemetry ingestion with idempotent event IDs.
- PostgreSQL persistence for playback sessions and telemetry events.
- Online logistic model with explicit features and inspectable weights.
- Persistent model registry with versioned checkpoints and holdout evaluation metrics.
- Policy layer that separates risk prediction from bitrate selection.
- WebSocket updates for live session dashboards.
- Analytics summary for throughput, bitrate, rebuffer rate, and latency.
- Prometheus metrics for telemetry ingestion and recommendation latency.

## Technology

- Frontend: React, TypeScript, Vite
- API: Python, FastAPI, Pydantic, SQLAlchemy
- Model: online logistic QoE model with a threshold-based bitrate policy
- Storage: PostgreSQL
- Operations: Docker Compose, GitHub Actions, WebSockets, Prometheus metrics

## Getting started

### Start the services

```bash
npm install
docker compose up --build
```

The API is available at `http://localhost:8003`. FastAPI documentation is available at `http://localhost:8003/docs`, and metrics are exposed at `http://localhost:8003/metrics`.

### Start the frontend

```bash
npm run dev
```

## API surface

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/sessions` | Create a playback session |
| `GET` | `/api/v1/sessions` | List recent playback sessions |
| `POST` | `/api/v1/sessions/:id/telemetry` | Ingest a batch of playback events |
| `GET` | `/api/v1/sessions/:id/recommendation` | Get a quality recommendation |
| `POST` | `/api/v1/model/retrain` | Retrain the online model from stored events |
| `GET` | `/api/v1/model/status` | Read the active model version and evaluation metadata |
| `GET` | `/api/v1/analytics/summary` | Read aggregate playback statistics |
| `WS` | `/ws/sessions/:id` | Stream live session updates |
| `GET` | `/healthz` | Check database connectivity and service health |
| `GET` | `/metrics` | Export Prometheus metrics |

## Validation

```bash
pytest -q backend/tests
npm run build
npm run typecheck
```

The backend tests cover telemetry idempotency, recommendations, model updates, versioned retraining and restore behavior, analytics, and WebSocket-related service behavior. The GitHub Actions workflow also runs a PostgreSQL API round-trip integration test. With PostgreSQL running locally, execute it with:

```bash
CINESCALER_INTEGRATION=1 \
DATABASE_URL=postgresql+psycopg://cinescaler:cinescaler@localhost:5432/cinescaler \
pytest -q backend/tests/test_postgres_integration.py
```

## Reproducible load measurement

The [GitHub Actions benchmark run](https://github.com/MarthalaJagruthiReddy/cinescaler/actions/runs/34620889499) used PostgreSQL 16, 20 concurrent clients, 250 telemetry requests, and 250 recommendation requests:

| Endpoint | Throughput | p50 / p95 / p99 latency | Errors |
| --- | ---: | ---: | ---: |
| `POST /api/v1/sessions/:id/telemetry` | 297.57 requests/sec | 65.55 / 72.68 / 76.30 ms | 0 / 250 |
| `GET /api/v1/sessions/:id/recommendation` | 1,234.61 requests/sec | 15.71 / 16.28 / 16.84 ms | 0 / 250 |

These are measurements from that CI runner and workload, not production capacity guarantees. Re-run the benchmark workflow before comparing code changes.

## Repository layout

```text
backend/app/ml/    Online QoE model
backend/app/       FastAPI routes, persistence, metrics, and schemas
frontend/          React streaming dashboard
docker-compose.yml PostgreSQL and API services
```

## Next steps

- Add offline trace replay and comparisons against configurable baseline policies.
- Add rollback and side-by-side comparison endpoints for stored model versions.
- Add retention and partitioning strategies for high-volume telemetry, then repeat the benchmark at larger volumes.
