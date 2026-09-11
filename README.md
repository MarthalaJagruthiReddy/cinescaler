# CineScaler

CineScaler is an adaptive streaming lab. A playback client sends throughput, buffer, latency, bitrate, and rebuffer events; an online logistic model updates from those observations and recommends the highest quality profile below a predicted rebuffer-risk threshold.

## Engineering signals

- Batch telemetry ingestion with idempotent event IDs.
- PostgreSQL persistence for sessions and time-series-like event data.
- Explainable online learning with explicit features and inspectable weights.
- A policy layer separates prediction from the bitrate decision.
- WebSocket channel for live dashboard updates.
- Prometheus latency and throughput metrics plus an analytics summary endpoint.

The model is intentionally small and explainable. It is a portfolio system, not a claim that a five-profile simulator reproduces Netflix's production ABR stack.

## Run

```bash
npm install
docker compose up --build
```

Open `http://localhost:8003/docs`. Run the frontend with:

```bash
npm run dev
```

## Interview discussion

1. Why should telemetry ingestion be idempotent when a player reconnects?
2. What is the difference between the model's predicted risk and the policy's chosen bitrate?
3. How would you partition and retain billions of playback events?
4. How would you run an A/B test against a baseline ABR algorithm without harming users?

## Honest benchmark plan

Generate identical bandwidth traces, compare a fixed-bitrate baseline with the model policy, and report rebuffer ratio, average delivered bitrate, bitrate-switch count, p95 recommendation latency, and cold-start behavior. Use confidence intervals before putting a number on the resume.
