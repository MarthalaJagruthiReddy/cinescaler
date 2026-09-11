from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PlaybackSession(Base):
    __tablename__ = "playback_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    device: Mapped[str] = mapped_column(String(80), default="browser")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("playback_sessions.id", ondelete="CASCADE"), index=True)
    throughput_mbps: Mapped[float] = mapped_column(Float)
    buffer_seconds: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[float] = mapped_column(Float)
    bitrate_mbps: Mapped[float] = mapped_column(Float)
    rebuffered: Mapped[bool] = mapped_column(Boolean, default=False)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
