from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = Field(default="Demo stream", min_length=1, max_length=200)
    device: str = Field(default="browser", min_length=1, max_length=80)


class SessionRead(BaseModel):
    id: str
    title: str
    device: str
    created_at: datetime


class TelemetryEventCreate(BaseModel):
    event_id: str = Field(min_length=4, max_length=80)
    throughput_mbps: float = Field(gt=0, le=1_000)
    buffer_seconds: float = Field(ge=0, le=120)
    latency_ms: float = Field(ge=0, le=10_000)
    bitrate_mbps: float = Field(gt=0, le=100)
    rebuffered: bool = False
    metadata: dict = Field(default_factory=dict)


class TelemetryBatch(BaseModel):
    events: list[TelemetryEventCreate] = Field(min_length=1, max_length=100)


class Recommendation(BaseModel):
    bitrate_mbps: float
    quality_label: str
    predicted_rebuffer_risk: float
    confidence: float
    rationale: str


class Summary(BaseModel):
    sessions: int
    events: int
    average_throughput_mbps: float
    average_bitrate_mbps: float
    rebuffer_rate: float
    average_latency_ms: float
