"use client";

import React, { useEffect, useRef, useState } from "react";
import type { RTSPStream, RTSPTestResult } from "@/types";
import { API } from "@/lib/api"; // FastAPI base URL จาก .env.local (NEXT_PUBLIC_API_URL)

// ─── Mock seed streams ────────────────────────────────────────

const SEED_STREAMS: RTSPStream[] = [
  { camera_id: "CAM-01", rtsp_url: "rtsp://192.168.1.101:554/live", label: "Main Entrance", status: "live", resolution: "1920x1080", fps: 25 },
  { camera_id: "CAM-02", rtsp_url: "rtsp://192.168.1.102:554/ch0", label: "Corridor B", status: "live", resolution: "1280x720", fps: 30 },
  { camera_id: "CAM-03", rtsp_url: "rtsp://192.168.1.103:554/main", label: "Parking Lot", status: "offline", resolution: undefined, fps: undefined },
  { camera_id: "CAM-04", rtsp_url: "rtsp://192.168.1.104:554/stream", label: "Exit Gate", status: "error", resolution: undefined, fps: undefined },
];

// ─── Helpers ─────────────────────────────────────────────────

const STATUS_STYLE: Record<RTSPStream["status"], { text: string; border: string; bg: string; dot: string }> = {
  live: { text: "text-green-400", border: "border-green-800/60", bg: "bg-green-950/30", dot: "bg-green-500 animate-pulse" },
  offline: { text: "text-slate-500", border: "border-slate-700/60", bg: "bg-slate-900/30", dot: "bg-slate-600" },
  error: { text: "text-red-400", border: "border-red-800/60", bg: "bg-red-950/20", dot: "bg-red-500" },
};

const CAMERA_ACCENTS: Record<string, { text: string; border: string }> = {
  "CAM-01": { text: "text-cyan-400", border: "border-cyan-900" },
  "CAM-02": { text: "text-pink-400", border: "border-pink-900" },
  "CAM-03": { text: "text-yellow-400", border: "border-yellow-900" },
  "CAM-04": { text: "text-purple-400", border: "border-purple-900" },
};
const DEFAULT_ACCENT = { text: "text-slate-400", border: "border-slate-700" };

function isValidRTSP(url: string) {
  return /^rtsp:\/\/.{3,}/.test(url.trim());
}

// ─── Component ───────────────────────────────────────────────

export default function RTSPTab() {
  const [streams, setStreams] = useState<RTSPStream[]>(SEED_STREAMS);
  const [formUrl, setFormUrl] = useState("");
  const [formCamId, setFormCamId] = useState("");
  const [formLabel, setFormLabel] = useState("");
  const [formErrors, setFormErrors] = useState<{ url?: string; camId?: string }>({});
  const [testResult, setTestResult] = useState<RTSPTestResult | null>(null);
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "done">("idle");
  const [addStatus, setAddStatus] = useState<"idle" | "adding" | "done" | "error">("idle");
  const [selectedStream, setSelectedStream] = useState<RTSPStream | null>(null);
  const [activeStreams, setActiveStreams] = useState<string[]>([]);
  const [stoppingCams, setStoppingCams] = useState<Set<string>>(new Set());
  const addTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Poll active AI streams every 5s ───────────────────────
  useEffect(() => {
    const poll = async () => {
      try {
        // เรียก FastAPI โดยตรง — ไม่ผ่าน Next.js proxy
        const r = await fetch(`${API}/api/video/active-streams`);
        if (r.ok) { const d = await r.json(); setActiveStreams(d.active ?? []); }
      } catch { /* ignore */ }
    };
    poll();
    const t = setInterval(poll, 5000);
    return () => clearInterval(t);
  }, []);

  // ── Simulate periodic FPS jitter ──────────────────────────
  useEffect(() => {
    const t = setInterval(() => {
      setStreams((prev) =>
        prev.map((s) => {
          if (s.status === "live" && Math.random() < 0.02) {
            return { ...s, fps: Math.max(20, (s.fps ?? 25) + Math.floor((Math.random() - 0.5) * 4)) };
          }
          return s;
        })
      );
    }, 3000);
    return () => clearInterval(t);
  }, []);

  // ── Test RTSP connection ───────────────────────────────────
  const handleTest = async () => {
    const url = formUrl.trim();
    if (!isValidRTSP(url)) {
      setFormErrors((e) => ({ ...e, url: "Must start with rtsp://" }));
      return;
    }
    setTestStatus("testing");
    setTestResult(null);

    try {
      const res = await fetch("/api/input/test-rtsp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rtsp_url: url }),
      });
      const data: RTSPTestResult = await res.json();
      setTestResult(data);
    } catch {
      // Simulate in dev
      await new Promise((r) => setTimeout(r, 1200));
      const mock: RTSPTestResult = Math.random() > 0.3
        ? { reachable: true, latency_ms: 40 + Math.floor(Math.random() * 80), resolution: "1920x1080", fps: 25 }
        : { reachable: false, error: "Connection refused or host unreachable" };
      setTestResult(mock);
    }

    setTestStatus("done");
  };

  // ── Add stream ─────────────────────────────────────────────
  const handleAdd = async () => {
    const errors: { url?: string; camId?: string } = {};
    if (!isValidRTSP(formUrl)) errors.url = "Must start with rtsp://";
    if (!formCamId.trim()) errors.camId = "Camera ID is required";
    if (Object.keys(errors).length) { setFormErrors(errors); return; }

    if (streams.find((s) => s.camera_id === formCamId.trim().toUpperCase())) {
      setFormErrors({ camId: "Camera ID already exists" });
      return;
    }

    setAddStatus("adding");

    try {
      await fetch("/api/input/rtsp-streams", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rtsp_url: formUrl, camera_id: formCamId.trim().toUpperCase(), label: formLabel || formCamId }),
      });
    } catch { /* offline dev */ }

    await new Promise((r) => setTimeout(r, 800));

    const newStream: RTSPStream = {
      camera_id: formCamId.trim().toUpperCase(),
      rtsp_url: formUrl.trim(),
      label: formLabel.trim() || formCamId.trim().toUpperCase(),
      status: testResult?.reachable ? "live" : "offline",
      resolution: testResult?.resolution,
      fps: testResult?.fps,
    };

    setStreams((prev) => [newStream, ...prev]);
    setAddStatus("done");
    setFormUrl(""); setFormCamId(""); setFormLabel("");
    setTestResult(null); setTestStatus("idle");
    setFormErrors({});

    if (addTimeoutRef.current) clearTimeout(addTimeoutRef.current);
    addTimeoutRef.current = setTimeout(() => setAddStatus("idle"), 2000);
  };

  // ── Remove stream ──────────────────────────────────────────
  const handleRemove = async (camId: string) => {
    try {
      await fetch(`/api/input/rtsp-streams?camera_id=${camId}`, { method: "DELETE" });
    } catch { /* offline */ }
    setStreams((prev) => prev.filter((s) => s.camera_id !== camId));
    if (selectedStream?.camera_id === camId) setSelectedStream(null);
  };

  // ── Toggle stream status (simulate reconnect) ──────────────
  const handleToggle = (camId: string) => {
    setStreams((prev) =>
      prev.map((s) =>
        s.camera_id === camId
          ? { ...s, status: s.status === "live" ? "offline" : "live" }
          : s
      )
    );
  };

  // ── Stop AI processing ────────────────────────────────────
  const handleStop = async (camId: string) => {
    setStoppingCams((s) => new Set(s).add(camId));
    try {
      // เรียก FastAPI โดยตรง — stop AI processing
      await fetch(`${API}/api/video/stop/${encodeURIComponent(camId)}`, { method: "POST" });
      setActiveStreams((prev) => prev.filter((id) => id !== camId));
    } catch { /* ignore */ }
    setStoppingCams((s) => { const n = new Set(s); n.delete(camId); return n; });
  };

  const liveCount = streams.filter((s) => s.status === "live").length;

  return (
    <div className="flex gap-4 h-full min-h-0">
      {/* ── Left: Add form ── */}
      <div className="w-80 flex-shrink-0 flex flex-col gap-3">
        <div className="hud-panel p-4 flex flex-col gap-3">
          <div className="font-orbitron text-xs font-bold text-slate-400 tracking-[0.2em] mb-1">
            ADD NEW STREAM
          </div>

          {/* RTSP URL */}
          <FormField
            label="RTSP URL"
            required
            error={formErrors.url}
            hint="rtsp://user:pass@host:port/path"
          >
            <div className="flex gap-2">
              <input
                type="text"
                value={formUrl}
                onChange={(e) => { setFormUrl(e.target.value); setFormErrors((x) => ({ ...x, url: undefined })); setTestStatus("idle"); setTestResult(null); }}
                placeholder="rtsp://192.168.1.x:554/live"
                className={`
                  flex-1 bg-slate-900/60 border rounded-sm px-3 py-1.5 font-mono text-[10px]
                  text-slate-300 placeholder-slate-700 outline-none tracking-wide transition-colors
                  ${formErrors.url ? "border-red-700/60" : "border-slate-700/60 focus:border-yellow-600/60"}
                `}
              />
            </div>
          </FormField>

          {/* Test button + result */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleTest}
              disabled={!formUrl || testStatus === "testing"}
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded-sm border font-mono text-[9px] tracking-wider
                transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed
                ${testStatus === "testing"
                  ? "border-cyan-800/60 text-cyan-500 bg-cyan-950/30 cursor-wait"
                  : "border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-300"
                }
              `}
            >
              {testStatus === "testing" ? (
                <><PingAnimation /> TESTING...</>
              ) : (
                <><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-3 h-3">
                  <path d="M5 12.55a11 11 0 0114.08 0M1.42 9a16 16 0 0121.16 0M8.53 16.11a6 6 0 016.95 0M12 20h.01" />
                </svg> TEST CONNECTION</>
              )}
            </button>

            {/* Test result badge */}
            {testStatus === "done" && testResult && (
              <TestResultBadge result={testResult} />
            )}
          </div>

          {/* Camera ID */}
          <FormField label="CAMERA ID" required error={formErrors.camId}>
            <input
              type="text"
              value={formCamId}
              onChange={(e) => { setFormCamId(e.target.value.toUpperCase()); setFormErrors((x) => ({ ...x, camId: undefined })); }}
              placeholder="e.g. CAM-05"
              maxLength={20}
              className={`
                w-full bg-slate-900/60 border rounded-sm px-3 py-1.5 font-mono text-[10px]
                text-slate-300 placeholder-slate-700 outline-none tracking-widest uppercase transition-colors
                ${formErrors.camId ? "border-red-700/60" : "border-slate-700/60 focus:border-yellow-600/60"}
              `}
            />
          </FormField>

          {/* Label (optional) */}
          <FormField label="DISPLAY NAME" hint="Optional friendly name">
            <input
              type="text"
              value={formLabel}
              onChange={(e) => setFormLabel(e.target.value)}
              placeholder="e.g. Rooftop Cam"
              className="w-full bg-slate-900/60 border border-slate-700/60 rounded-sm px-3 py-1.5
                font-mono text-[10px] text-slate-300 placeholder-slate-700 outline-none
                focus:border-yellow-600/60 transition-colors tracking-wide"
            />
          </FormField>

          {/* Add button */}
          <button
            onClick={handleAdd}
            disabled={addStatus === "adding"}
            className={`
              w-full flex items-center justify-center gap-2 py-2.5 rounded-sm border
              font-orbitron text-[10px] font-bold tracking-[0.2em] transition-all duration-200
              disabled:cursor-wait
              ${addStatus === "done"
                ? "border-green-700/60 bg-green-950/30 text-green-400"
                : addStatus === "adding"
                  ? "border-yellow-800/60 bg-yellow-950/30 text-yellow-500"
                  : "border-yellow-600/60 bg-yellow-950/30 text-yellow-400 hover:bg-yellow-900/40 hover:border-yellow-500 shadow-[0_0_10px_rgba(255,215,0,0.1)] hover:shadow-[0_0_18px_rgba(255,215,0,0.2)]"
              }
            `}
          >
            {addStatus === "done" ? (
              <><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3.5 h-3.5"><path d="M20 6L9 17l-5-5" /></svg> ADDED</>
            ) : addStatus === "adding" ? (
              <><PingAnimation /> CONNECTING...</>
            ) : (
              <><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3.5 h-3.5"><path d="M12 5v14M5 12h14" /></svg> ADD STREAM</>
            )}
          </button>
        </div>

        {/* Tips panel */}
        <div className="hud-panel p-3">
          <div className="font-mono text-[10px] text-slate-600 tracking-[0.2em] mb-2">FORMAT EXAMPLES</div>
          {[
            { label: "Hikvision", url: "rtsp://admin:pass@ip:554/h264/ch1/main/av_stream" },
            { label: "Dahua", url: "rtsp://admin:pass@ip:554/cam/realmonitor?channel=1" },
            { label: "Generic", url: "rtsp://user:pass@host:554/live" },
          ].map(({ label, url }) => (
            <button
              key={label}
              onClick={() => setFormUrl(url)}
              className="w-full text-left mb-1 group"
            >
              <span className="font-mono text-[9px] text-slate-600 group-hover:text-slate-400 transition-colors">
                <span className="text-slate-700 mr-1">{label}:</span>
                {url}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* ── Right: Streams table ── */}
      <div className="flex-1 flex flex-col hud-panel min-h-0 min-w-0">
        {/* Table header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800/60 flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="font-orbitron text-xs font-bold text-slate-400 tracking-[0.2em]">ACTIVE STREAMS</span>
            <div className="flex items-center gap-1">
              <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              <span className="font-mono text-[10px] text-green-500">{liveCount} LIVE</span>
            </div>
            <span className="font-mono text-[10px] text-slate-600">/ {streams.length} TOTAL</span>
          </div>
          <button className="font-mono text-[8px] text-slate-600 hover:text-slate-400 transition-colors">
            REFRESH ALL
          </button>
        </div>

        {/* Column headers */}
        <div className="grid gap-2 px-4 py-1.5 border-b border-slate-800/30 flex-shrink-0"
          style={{ gridTemplateColumns: "90px 1fr 110px 90px 70px 60px 110px 110px" }}>
          {["CAM ID", "URL / LABEL", "STATUS", "RESOLUTION", "FPS", "LAT", "AI STATUS", "ACTIONS"].map((h) => (
            <span key={h} className="font-mono text-[9px] text-slate-700 tracking-widest uppercase">{h}</span>
          ))}
        </div>

        {/* Rows */}
        <div className="flex-1 overflow-y-auto min-h-0 divide-y divide-slate-800/30">
          {streams.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center gap-3 py-12">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-10 h-10 text-slate-800">
                <path d="M15 10l4.553-2.277A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
              </svg>
              <p className="font-mono text-[9px] text-slate-700 tracking-widest">NO STREAMS CONFIGURED</p>
            </div>
          ) : (
            streams.map((stream) => (
              <StreamRow
                key={stream.camera_id}
                stream={stream}
                selected={selectedStream?.camera_id === stream.camera_id}
                isProcessing={activeStreams.includes(stream.camera_id)}
                isStopping={stoppingCams.has(stream.camera_id)}
                onSelect={() => setSelectedStream(stream.camera_id === selectedStream?.camera_id ? null : stream)}
                onRemove={() => handleRemove(stream.camera_id)}
                onToggle={() => handleToggle(stream.camera_id)}
                onStop={() => handleStop(stream.camera_id)}
              />
            ))
          )}
        </div>

        {/* Summary bar */}
        <div className="border-t border-slate-800/30 px-4 py-2 flex-shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-4">
            {(["live", "offline", "error"] as RTSPStream["status"][]).map((s) => {
              const count = streams.filter((x) => x.status === s).length;
              const st = STATUS_STYLE[s];
              return (
                <div key={s} className="flex items-center gap-1.5">
                  <div className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
                  <span className={`font-mono text-[10px] ${st.text}`}>{count} {s.toUpperCase()}</span>
                </div>
              );
            })}
          </div>
          <span className="font-mono text-[8px] text-slate-700">
            {streams.reduce((acc, s) => acc + (s.fps ?? 0), 0)} TOTAL FPS
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── Stream Row ───────────────────────────────────────────────

function StreamRow({
  stream,
  selected,
  isProcessing,
  isStopping,
  onSelect,
  onRemove,
  onToggle,
  onStop,
}: {
  stream: RTSPStream;
  selected: boolean;
  isProcessing: boolean;
  isStopping: boolean;
  onSelect: () => void;
  onRemove: () => void;
  onToggle: () => void;
  onStop: () => void;
}) {
  const style = STATUS_STYLE[stream.status];
  const accent = CAMERA_ACCENTS[stream.camera_id] ?? DEFAULT_ACCENT;
  const [confirmRemove, setConfirmRemove] = useState(false);

  const handleRemoveClick = () => {
    if (confirmRemove) { onRemove(); }
    else {
      setConfirmRemove(true);
      setTimeout(() => setConfirmRemove(false), 2500);
    }
  };

  return (
    <div
      className={`
        grid gap-2 px-4 py-2.5 items-center cursor-pointer transition-all
        ${selected ? "bg-slate-800/40" : "hover:bg-slate-900/30"}
        ${isProcessing ? "border-l-2 border-cyan-500/40" : "border-l-2 border-transparent"}
      `}
      style={{ gridTemplateColumns: "90px 1fr 110px 90px 70px 60px 110px 110px" }}
      onClick={onSelect}
    >
      {/* Cam ID */}
      <span className={`font-mono text-xs font-bold ${accent.text} border ${accent.border} px-1.5 py-0.5 rounded-sm inline-block w-fit`}>
        {stream.camera_id}
      </span>

      {/* URL / Label */}
      <div className="min-w-0">
        <div className="font-mono text-xs text-slate-300 truncate">{stream.label ?? stream.camera_id}</div>
        <div className="font-mono text-[10px] text-slate-600 truncate">{stream.rtsp_url}</div>
      </div>

      {/* Status */}
      <div className="flex items-center gap-1.5">
        <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${style.dot}`} />
        <span className={`font-mono text-[10px] ${style.text}`}>{stream.status.toUpperCase()}</span>
      </div>

      {/* Resolution */}
      <span className="font-mono text-[10px] text-slate-400">{stream.resolution ?? "—"}</span>

      {/* FPS */}
      <span className="font-mono text-[10px] text-slate-400 tabular-nums">
        {stream.fps != null ? <><span className="text-cyan-400">{stream.fps}</span> fps</> : "—"}
      </span>

      {/* Latency placeholder */}
      <span className="font-mono text-[9px] text-slate-600">
        {stream.status === "live" ? `${30 + Math.floor(Math.random() * 20)}ms` : "—"}
      </span>

      {/* AI STATUS */}
      <div>
        {isProcessing ? (
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
            <span className="font-mono text-[9px] text-cyan-400 tracking-widest">ANALYZING</span>
          </div>
        ) : (
          <span className="font-mono text-[9px] text-slate-700">—</span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
        {/* Toggle */}
        <button
          onClick={onToggle}
          title={stream.status === "live" ? "Pause stream" : "Resume stream"}
          className={`p-1 rounded-sm border transition-colors ${stream.status === "live"
            ? "border-slate-700 text-slate-500 hover:border-yellow-700 hover:text-yellow-400"
            : "border-slate-700 text-slate-600 hover:border-green-700 hover:text-green-400"
            }`}
        >
          {stream.status === "live" ? (
            <svg viewBox="0 0 24 24" fill="currentColor" className="w-3 h-3"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="currentColor" className="w-3 h-3"><path d="M8 5v14l11-7z" /></svg>
          )}
        </button>

        {/* STOP AI */}
        {isProcessing && (
          <button
            onClick={onStop}
            disabled={isStopping}
            title="Stop AI prediction"
            className="p-1 rounded-sm border border-cyan-800/60 text-cyan-500 hover:border-red-600/60 hover:text-red-400 transition-colors disabled:opacity-40"
          >
            {isStopping ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3 animate-spin"><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48 2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48 2.83-2.83" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="currentColor" className="w-3 h-3"><rect x="6" y="6" width="12" height="12" rx="1" /></svg>
            )}
          </button>
        )}

        {/* Remove */}
        <button
          onClick={handleRemoveClick}
          title={confirmRemove ? "Click again to confirm" : "Remove stream"}
          className={`p-1 rounded-sm border transition-all ${confirmRemove
            ? "border-red-600/60 text-red-400 bg-red-950/30 animate-pulse"
            : "border-slate-700 text-slate-600 hover:border-red-700/60 hover:text-red-400"
            }`}
        >
          {confirmRemove ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3 h-3">
              <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3">
              <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14H6L5 6M10 11v6M14 11v6M9 6V4h6v2" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}

// ─── Small sub-components ─────────────────────────────────────

function FormField({
  label,
  required,
  error,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="font-mono text-[10px] text-slate-500 tracking-[0.2em] uppercase flex items-center gap-1 mb-1">
        {label}
        {required && <span className="text-red-500">*</span>}
        {hint && <span className="text-slate-700 normal-case tracking-normal">· {hint}</span>}
      </label>
      {children}
      {error && <p className="font-mono text-[10px] text-red-400 mt-0.5 tracking-wide">{error}</p>}
    </div>
  );
}

function TestResultBadge({ result }: { result: RTSPTestResult }) {
  if (result.reachable) {
    return (
      <div className="flex items-center gap-1.5 px-2 py-1 rounded-sm border border-green-800/60 bg-green-950/30">
        <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
        <span className="font-mono text-[8px] text-green-400">
          OK · {result.latency_ms}ms
          {result.resolution && ` · ${result.resolution}`}
        </span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1.5 px-2 py-1 rounded-sm border border-red-800/60 bg-red-950/30">
      <div className="w-1.5 h-1.5 rounded-full bg-red-500" />
      <span className="font-mono text-[8px] text-red-400">UNREACHABLE</span>
    </div>
  );
}

function PingAnimation() {
  return (
    <div className="relative w-3 h-3 flex-shrink-0">
      <div className="absolute inset-0 border border-current rounded-full animate-ping opacity-40" />
      <div className="absolute inset-0.5 border border-current rounded-full" />
    </div>
  );
}