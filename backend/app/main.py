from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Response, WebSocket, WebSocketDisconnect, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import Integer, cast, func, select, text
from sqlalchemy.orm import Session

from .db import Base, build_engine, build_session_factory, session_dependency
from .metrics import recommendation_latency, recommendations_served, telemetry_events_ingested
from .ml.model import QoEModel
from .models import PlaybackSession, TelemetryEvent
from .schemas import Recommendation, SessionCreate, SessionRead, Summary, TelemetryBatch


class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections[session_id].add(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket):
        self.connections[session_id].discard(websocket)

    async def broadcast(self, session_id: str, message: dict):
        disconnected = []
        for websocket in self.connections[session_id]:
            try:
                await websocket.send_json(message)
            except Exception:  # noqa: BLE001 - stale browser connections are disposable.
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(session_id, websocket)


def create_app(database_url: str | None = None, model: QoEModel | None = None) -> FastAPI:
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    abr_model = model or QoEModel()
    manager = ConnectionManager()
    app = FastAPI(title="CineScaler API", version="0.1.0", description="Telemetry-driven adaptive bitrate experimentation.")
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.abr_model = abr_model

    def get_session():
        yield from session_dependency(factory)

    @app.get("/healthz")
    def healthz(session: Session = Depends(get_session)):
        session.execute(text("SELECT 1"))
        return {"status": "ok", "service": "cinescaler", "model": "online-logistic-qoe"}

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/api/v1/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
    def create_session(command: SessionCreate, session: Session = Depends(get_session)):
        item = PlaybackSession(id=str(uuid.uuid4()), title=command.title, device=command.device)
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    @app.get("/api/v1/sessions", response_model=list[SessionRead])
    def list_sessions(session: Session = Depends(get_session)):
        return list(session.scalars(select(PlaybackSession).order_by(PlaybackSession.created_at.desc()).limit(20)))

    @app.post("/api/v1/sessions/{session_id}/telemetry")
    async def ingest_telemetry(
        batch: TelemetryBatch,
        session_id: Annotated[str, Path(min_length=36, max_length=36)],
        session: Session = Depends(get_session),
    ):
        playback = session.get(PlaybackSession, session_id)
        if not playback:
            raise HTTPException(status_code=404, detail="Playback session not found")
        accepted = 0
        for event in batch.events:
            if session.get(TelemetryEvent, event.event_id):
                continue
            session.add(TelemetryEvent(id=event.event_id, session_id=session_id, throughput_mbps=event.throughput_mbps, buffer_seconds=event.buffer_seconds, latency_ms=event.latency_ms, bitrate_mbps=event.bitrate_mbps, rebuffered=event.rebuffered, event_metadata=event.metadata))
            abr_model.update(event.throughput_mbps, event.buffer_seconds, event.latency_ms, event.bitrate_mbps, event.rebuffered)
            accepted += 1
        session.commit()
        telemetry_events_ingested.inc(accepted)
        asyncio.create_task(manager.broadcast(session_id, {"type": "telemetry", "accepted": accepted}))
        return {"accepted": accepted, "duplicates_ignored": len(batch.events) - accepted}

    @app.get("/api/v1/sessions/{session_id}/recommendation", response_model=Recommendation)
    def recommendation(
        session_id: str,
        throughput_mbps: float = Query(gt=0, le=1_000),
        buffer_seconds: float = Query(ge=0, le=120),
        latency_ms: float = Query(ge=0, le=10_000),
    ):
        started = time.perf_counter()
        prediction = abr_model.recommend(throughput_mbps, buffer_seconds, latency_ms)
        recommendations_served.inc()
        recommendation_latency.observe(time.perf_counter() - started)
        label = "Ultra HD" if prediction.bitrate_mbps >= 8 else "Full HD" if prediction.bitrate_mbps >= 5 else "HD" if prediction.bitrate_mbps >= 3 else "SD"
        return Recommendation(bitrate_mbps=prediction.bitrate_mbps, quality_label=label, predicted_rebuffer_risk=round(prediction.risk, 4), confidence=round(1 - prediction.risk, 4), rationale=f"Selected the highest tested profile under the 35% predicted rebuffer threshold for {throughput_mbps:.1f} Mbps throughput and {buffer_seconds:.1f}s buffer.")

    @app.post("/api/v1/model/retrain")
    def retrain_model(session: Session = Depends(get_session)):
        events = list(session.scalars(select(TelemetryEvent)))
        samples = [{"throughput_mbps": event.throughput_mbps, "buffer_seconds": event.buffer_seconds, "latency_ms": event.latency_ms, "bitrate_mbps": event.bitrate_mbps, "rebuffered": event.rebuffered} for event in events]
        abr_model.retrain(samples)
        return {"samples": len(samples), "weights": [round(weight, 5) for weight in abr_model.weights]}

    @app.get("/api/v1/analytics/summary", response_model=Summary)
    def summary(session: Session = Depends(get_session)):
        event_count = session.scalar(select(func.count(TelemetryEvent.id))) or 0
        sessions = session.scalar(select(func.count(PlaybackSession.id))) or 0
        if not event_count:
            return Summary(sessions=sessions, events=0, average_throughput_mbps=0, average_bitrate_mbps=0, rebuffer_rate=0, average_latency_ms=0)
        averages = session.execute(select(func.avg(TelemetryEvent.throughput_mbps), func.avg(TelemetryEvent.bitrate_mbps), func.avg(TelemetryEvent.latency_ms), func.avg(cast(TelemetryEvent.rebuffered, Integer)))).one()
        return Summary(sessions=sessions, events=event_count, average_throughput_mbps=round(float(averages[0] or 0), 3), average_bitrate_mbps=round(float(averages[1] or 0), 3), rebuffer_rate=round(float(averages[3] or 0), 3), average_latency_ms=round(float(averages[2] or 0), 3))

    @app.websocket("/ws/sessions/{session_id}")
    async def session_stream(websocket: WebSocket, session_id: str):
        await manager.connect(session_id, websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(session_id, websocket)

    return app


app = create_app()
