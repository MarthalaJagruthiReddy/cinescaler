import { useCallback, useEffect, useMemo, useState } from "react";

type Recommendation = { bitrate_mbps: number; quality_label: string; predicted_rebuffer_risk: number; confidence: number; rationale: string };
type Summary = { sessions: number; events: number; average_throughput_mbps: number; average_bitrate_mbps: number; rebuffer_rate: number; average_latency_ms: number };
type ModelStatus = { version: number; trained_samples: number; metrics: { samples: number; accuracy: number; precision: number; recall: number; brier_score: number }; last_trained_at: string | null; training_samples?: number; evaluation_samples?: number };
type Session = { id: string; title: string; device: string };
type EventPoint = { throughput: number; buffer: number; bitrate: number; risk: number };

const API = import.meta.env.VITE_API_BASE ?? "http://localhost:8003";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  if (!response.ok) throw new Error((await response.json()).detail ?? "Request failed");
  return response.json() as Promise<T>;
}

function riskColor(risk: number) { return risk > .35 ? "#ff7878" : risk > .2 ? "#ffd166" : "#7af0c0"; }

const emptyModelStatus: ModelStatus = { version: 1, trained_samples: 0, metrics: { samples: 0, accuracy: 0, precision: 0, recall: 0, brier_score: 0 }, last_trained_at: null };

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [throughput, setThroughput] = useState(6);
  const [buffer, setBuffer] = useState(7);
  const [latency, setLatency] = useState(40);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [summary, setSummary] = useState<Summary>({ sessions: 0, events: 0, average_throughput_mbps: 0, average_bitrate_mbps: 0, rebuffer_rate: 0, average_latency_ms: 0 });
  const [modelStatus, setModelStatus] = useState<ModelStatus>(emptyModelStatus);
  const [history, setHistory] = useState<EventPoint[]>([]);
  const [notice, setNotice] = useState("Start a playback session to begin streaming telemetry.");

  const refreshSummary = useCallback(async () => { try { setSummary(await request<Summary>("/api/v1/analytics/summary")); } catch (error) { setNotice(error instanceof Error ? error.message : "API unavailable"); } }, []);
  const refreshModel = useCallback(async () => { try { setModelStatus(await request<ModelStatus>("/api/v1/model/status")); } catch (error) { setNotice(error instanceof Error ? error.message : "Model status unavailable"); } }, []);
  useEffect(() => { void refreshSummary(); void refreshModel(); }, [refreshModel, refreshSummary]);

  async function startSession() {
    const created = await request<Session>("/api/v1/sessions", { method: "POST", body: JSON.stringify({ title: "Portfolio demo stream", device: "browser" }) });
    setSession(created); setNotice("Live session established. Adjust the network controls and send a sample.");
  }

  async function sendTelemetry() {
    let activeSession = session;
    if (!activeSession) {
      activeSession = await request<Session>("/api/v1/sessions", { method: "POST", body: JSON.stringify({ title: "Portfolio demo stream", device: "browser" }) });
      setSession(activeSession);
    }
    const next = await request<Recommendation>(`/api/v1/sessions/${activeSession.id}/recommendation?throughput_mbps=${throughput}&buffer_seconds=${buffer}&latency_ms=${latency}`);
    const eventId = crypto.randomUUID();
    await request(`/api/v1/sessions/${activeSession.id}/telemetry`, { method: "POST", body: JSON.stringify({ events: [{ event_id: eventId, throughput_mbps: throughput, buffer_seconds: buffer, latency_ms: latency, bitrate_mbps: next.bitrate_mbps, rebuffered: next.predicted_rebuffer_risk > .55 }] }) });
    setRecommendation(next); setHistory((items) => [...items.slice(-7), { throughput, buffer, bitrate: next.bitrate_mbps, risk: next.predicted_rebuffer_risk }]); setNotice("Telemetry accepted; model weights updated online."); await refreshSummary();
  }

  async function retrainModel() {
    try {
      const next = await request<ModelStatus>("/api/v1/model/retrain", { method: "POST" });
      setModelStatus(next);
      setNotice(`Model v${next.version} trained on ${next.training_samples ?? next.trained_samples} samples and evaluated on ${next.evaluation_samples ?? next.metrics.samples}.`);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Model retraining failed"); }
  }

  const safePercent = useMemo(() => recommendation ? Math.max(4, Math.round((1 - recommendation.predicted_rebuffer_risk) * 100)) : 0, [recommendation]);

  return <main className="app">
    <header><div className="logo"><span className="logo-icon">◉</span><span>Cine<span>Scaler</span></span></div><div className="header-right"><span className="live"><i /> model stream live</span><span className="mono">MODEL / v{modelStatus.version}</span></div></header>
    <section className="hero"><div><p className="overline">PLAYBACK INTELLIGENCE LAB</p><h1>Keep the story<br /><span>moving.</span></h1><p className="hero-copy">An adaptive streaming control plane that learns from network conditions and protects the viewing experience one decision at a time.</p></div><button className="start" onClick={() => void startSession()}>{session ? "Session active" : "Start a session"}<span>↗</span></button></section>
    <section className="dashboard">
      <div className="control-panel panel"><div className="panel-head"><div><p className="overline">NETWORK SIMULATOR</p><h2>Shape the moment</h2></div><span className={`session-state ${session ? "on" : ""}`}><i />{session ? "recording" : "standby"}</span></div><p className="panel-copy">Change the conditions. The policy will select the highest profile below the learned rebuffer threshold.</p><div className="sliders"><label><span>Throughput <b>{throughput.toFixed(1)} Mbps</b></span><input type="range" min=".5" max="20" step=".5" value={throughput} onChange={(e) => setThroughput(Number(e.target.value))} /></label><label><span>Buffer <b>{buffer.toFixed(1)} sec</b></span><input type="range" min="0" max="20" step=".5" value={buffer} onChange={(e) => setBuffer(Number(e.target.value))} /></label><label><span>Latency <b>{latency} ms</b></span><input type="range" min="10" max="300" step="5" value={latency} onChange={(e) => setLatency(Number(e.target.value))} /></label></div><button className="send" onClick={() => void sendTelemetry()}>{session ? "Send telemetry sample" : "Create session & sample"}<span>→</span></button></div>
      <div className="decision-panel panel"><div className="panel-head"><div><p className="overline">POLICY DECISION</p><h2>Adaptive bitrate</h2></div><span className="ai-badge">ONLINE MODEL</span></div>{recommendation ? <><div className="decision-main"><div className="bitrate"><strong>{recommendation.bitrate_mbps}</strong><span>Mbps</span></div><div className="quality"><span>recommended profile</span><strong>{recommendation.quality_label}</strong><small>{recommendation.rationale}</small></div></div><div className="risk-row"><div><span>Predicted rebuffer risk</span><strong style={{ color: riskColor(recommendation.predicted_rebuffer_risk) }}>{Math.round(recommendation.predicted_rebuffer_risk * 100)}%</strong></div><div className="risk-track"><i style={{ width: `${safePercent}%`, background: riskColor(recommendation.predicted_rebuffer_risk) }} /></div><div className="confidence"><span>confidence</span><b>{Math.round(recommendation.confidence * 100)}%</b></div></div></> : <div className="decision-empty"><span>⌁</span><p>Send a telemetry sample to ask the policy for its next move.</p></div>}</div>
    </section>
    <section className="insights">
      <div className="history-panel panel"><div className="panel-head"><div><p className="overline">DECISION TRACE</p><h2>Recent samples</h2></div><span className="mono">{history.length.toString().padStart(2, "0")} points</span></div><div className="trace">{history.length ? history.map((point, index) => <div className="trace-row" key={`${point.throughput}-${index}`}><span className="trace-index">0{index + 1}</span><span className="trace-bar"><i style={{ width: `${Math.min(100, point.throughput / 20 * 100)}%` }} /></span><span className="trace-value">{point.throughput.toFixed(1)} Mbps</span><span className="trace-bitrate">→ {point.bitrate.toFixed(1)} Mbps</span><span className="trace-risk" style={{ color: riskColor(point.risk) }}>{Math.round(point.risk * 100)}% risk</span></div>) : <div className="empty-trace">Your telemetry trail will render here in real time.</div>}</div></div>
      <div className="metrics-panel panel"><p className="overline">SESSION TELEMETRY</p><h2>At a glance</h2><div className="metric-list"><div><span>Avg throughput</span><strong>{summary.average_throughput_mbps.toFixed(1)}<small> Mbps</small></strong></div><div><span>Avg delivered</span><strong>{summary.average_bitrate_mbps.toFixed(1)}<small> Mbps</small></strong></div><div><span>Rebuffer rate</span><strong>{Math.round(summary.rebuffer_rate * 100)}<small>%</small></strong></div><div><span>Avg latency</span><strong>{Math.round(summary.average_latency_ms)}<small> ms</small></strong></div></div><div className="model-status"><div className="model-status-head"><span>MODEL REGISTRY</span><b>v{modelStatus.version}</b></div><p>{modelStatus.trained_samples ? `${modelStatus.trained_samples} training samples · ${(modelStatus.metrics.accuracy * 100).toFixed(1)}% holdout accuracy` : "Collect telemetry, then evaluate a versioned checkpoint."}</p><button className="retrain" disabled={!summary.events} onClick={() => void retrainModel()}>Retrain + evaluate <span>↗</span></button></div></div>
    </section>
    <footer><span>CINESCALER / ADAPTIVE STREAMING SYSTEMS</span><span>{notice}</span></footer>
  </main>;
}
