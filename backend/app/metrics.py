from prometheus_client import Counter, Histogram


telemetry_events_ingested = Counter("cinescaler_telemetry_events_total", "Playback telemetry events accepted")
recommendations_served = Counter("cinescaler_recommendations_total", "Adaptive bitrate recommendations served")
recommendation_latency = Histogram("cinescaler_recommendation_latency_seconds", "Recommendation calculation latency")
