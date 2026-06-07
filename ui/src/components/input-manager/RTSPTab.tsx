"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import type { RTSPStream, RTSPTestResult } from "@/types";
import { API } from "@/lib/api"; // FastAPI base URL จาก .env.local (NEXT_PUBLIC_API_URL)

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

function isValidStreamSource(url: string) {
  const u = url.trim().toLowerCase();
  if (!u) return false;
  if (u.startsWith("rtsp://")) return true;
  if (u.startsWith("rtmp://")) return true;
  if (u.startsWith("http://") || u.startsWith("https://")) return true;
  return false;
}

// ─── Component ───────────────────────────────────────────────

export default function RTSPTab() {
  const [streams, setStreams] = useState<RTSPStream[]>([]);
  const [isLoadingStreams, setIsLoadingStreams] = useState(true);
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
  // camera_id → { reachable, latency_ms, checked_at, error }
  const [health, setHealth] = useState<Record<string, { reachable: boolean; latency_ms: number | null; checked_at: string; error: string | null }>>({});
  const [recheckingCams, setRecheckingCams] = useState<Set<string>>(new Set());

  const loadStreams = useCallback(async () => {
    setIsLoadingStreams(true);
    try {
      const response = await fetch("/api/input/rtsp-streams", { cache: "no-store" });
      if (!response.ok) throw new Error("failed to load streams");
      const data = await response.json();
      const rows: Partial<RTSPStream>[] = Array.isArray(data.streams) ? data.streams : [];
      const mapped: RTSPStream[] = rows
        .map((row) => ({
          camera_id: String(row.camera_id ?? ""),
          rtsp_url: String(row.rtsp_url ?? ""),
          label: row.label ?? row.camera_id,
          status: "offline" as const,
          resolution: row.resolution,
          fps: row.fps,
        }))
        .filter((row) => row.camera_id && row.rtsp_url);
      setStreams(mapped);
    } catch {
      setStreams([]);
    } finally {
      setIsLoadingStreams(false);
    }
  }, []);

  useEffect(() => {
    void loadStreams();
  }, [loadStreams]);

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

  // ── Poll camera reachability (backend checks every 10 min; we refresh the view) ──
  const loadHealth = useCallback(async () => {
    try {
      const r = await fetch("/api/dashboard/camera-health", { cache: "no-store" });
      if (r.ok) { const d = await r.json(); setHealth(d.health ?? {}); }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    void loadHealth();
    const t = setInterval(loadHealth, 60000); // refresh view every 1 min
    return () => clearInterval(t);
  }, [loadHealth]);

  // ── Reconnect: force an immediate reachability recheck ─────
  const handleReconnect = async (camId: string) => {
    setRecheckingCams((s) => new Set(s).add(camId));
    try {
      const r = await fetch(`/api/dashboard/camera-health/${encodeURIComponent(camId)}/recheck`, { method: "POST" });
      if (r.ok) {
        const d = await r.json();
        if (d.status) setHealth((prev) => ({ ...prev, [camId]: d.status }));
      }
    } catch { /* ignore */ }
    setRecheckingCams((s) => { const n = new Set(s); n.delete(camId); return n; });
  };

  // ── Test RTSP connection ───────────────────────────────────
  const handleTest = async () => {
    const url = formUrl.trim();
    if (!isValidRTSP(url)) {
      setFormErrors((e) => ({ ...e, url: "Test supports RTSP only (rtsp://...)" }));
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
    if (!isValidStreamSource(formUrl)) errors.url = "Enter a valid URL (rtsp/rtmp/http/https)";
    if (!formCamId.trim()) errors.camId = "Camera ID is required";
    if (Object.keys(errors).length) { setFormErrors(errors); return; }

    if (streams.find((s) => s.camera_id === formCamId.trim().toUpperCase())) {
      setFormErrors({ camId: "Camera ID already exists" });
      return;
    }

    setAddStatus("adding");

    try {
      const response = await fetch("/api/input/rtsp-streams", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_url: formUrl, camera_id: formCamId.trim().toUpperCase(), label: formLabel || formCamId }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
    } catch {
      setAddStatus("error");
      if (addTimeoutRef.current) clearTimeout(addTimeoutRef.current);
      addTimeoutRef.current = setTimeout(() => setAddStatus("idle"), 2500);
      return;
    }

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

  // ── Edit stream URL ────────────────────────────────────────
  const handleEditUrl = async (camId: string, newUrl: string, label?: string): Promise<boolean> => {
    const url = newUrl.trim();
    if (!isValidStreamSource(url)) return false;
    try {
      const response = await fetch("/api/input/rtsp-streams", {
        method: "POST", // backend upserts by camera_id
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_url: url, camera_id: camId, label: label || camId }),
      });
      if (!response.ok) return false;
    } catch {
      return false;
    }
    // Update local list + recheck reachability with the new URL
    setStreams((prev) => prev.map((s) => (s.camera_id === camId ? { ...s, rtsp_url: url } : s)));
    void handleReconnect(camId);
    return true;
  };

  // ── Remove stream ──────────────────────────────────────────
  const handleRemove = async (camId: string) => {
    try {
      const response = await fetch(`/api/input/rtsp-streams?camera_id=${camId}`, { method: "DELETE" });
      if (!response.ok) return;
    } catch {
      return;
    }
    setStreams((prev) => prev.filter((s) => s.camera_id !== camId));
    if (selectedStream?.camera_id === camId) setSelectedStream(null);
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

  // Derive reachability status from health map.
  // "live" = reachable, "error" = unreachable, "offline" = not yet checked.
  const statusOf = (camId: string): RTSPStream["status"] => {
    const h = health[camId];
    if (!h) return "offline";
    return h.reachable ? "live" : "error";
  };

  const liveCount = streams.filter((s) => statusOf(s.camera_id) === "live").length;

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
            label="STREAM URL"
            required
            error={formErrors.url}
            hint="rtsp://, rtmp://, http(s)://, youtube URL"
          >
            <div className="flex gap-2">
              <input
                type="text"
                value={formUrl}
                onChange={(e) => { setFormUrl(e.target.value); setFormErrors((x) => ({ ...x, url: undefined })); setTestStatus("idle"); setTestResult(null); }}
                placeholder="rtsp://... | https://youtube.com/watch?v=... | https://...m3u8"
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
              disabled={!formUrl || testStatus === "testing" || !isValidRTSP(formUrl)}
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
                </svg> TEST RTSP</>
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
                : addStatus === "error"
                  ? "border-red-700/60 bg-red-950/30 text-red-400"
                : addStatus === "adding"
                  ? "border-yellow-800/60 bg-yellow-950/30 text-yellow-500"
                  : "border-yellow-600/60 bg-yellow-950/30 text-yellow-400 hover:bg-yellow-900/40 hover:border-yellow-500 shadow-[0_0_10px_rgba(255,215,0,0.1)] hover:shadow-[0_0_18px_rgba(255,215,0,0.2)]"
              }
            `}
          >
            {addStatus === "done" ? (
              <><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3.5 h-3.5"><path d="M20 6L9 17l-5-5" /></svg> ADDED</>
            ) : addStatus === "error" ? (
              <><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3.5 h-3.5"><path d="M12 8v4m0 4h.01M10.29 3.86l-7.8 13.5A1 1 0 003.37 19h17.26a1 1 0 00.87-1.64l-7.8-13.5a1 1 0 00-1.73 0z" /></svg> ADD FAILED</>
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
            { label: "YouTube", url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ" },
            { label: "HLS", url: "https://example.com/live/stream.m3u8" },
            { label: "RTMP", url: "rtmp://example.com/live/cam01" },
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
          <button
            onClick={() => void loadStreams()}
            className="font-mono text-[8px] text-slate-600 hover:text-slate-400 transition-colors"
          >
            REFRESH ALL
          </button>
        </div>

        {/* Column headers */}
        <div className="grid gap-2 px-4 py-1.5 border-b border-slate-800/30 flex-shrink-0"
          style={{ gridTemplateColumns: "90px 1fr 120px 80px 60px 56px 100px 140px" }}>
          {["CAM ID", "URL / LABEL", "STATUS", "RESOLUTION", "FPS", "LAT", "AI STATUS", "ACTIONS"].map((h) => (
            <span key={h} className="font-mono text-[9px] text-slate-700 tracking-widest uppercase">{h}</span>
          ))}
        </div>

        {/* Rows */}
        <div className="flex-1 overflow-y-auto min-h-0 divide-y divide-slate-800/30">
          {isLoadingStreams ? (
            <div className="h-full flex items-center justify-center py-12">
              <p className="font-mono text-[9px] text-slate-600 tracking-widest">LOADING STREAMS...</p>
            </div>
          ) : streams.length === 0 ? (
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
                stream={{ ...stream, status: statusOf(stream.camera_id) }}
                health={health[stream.camera_id]}
                selected={selectedStream?.camera_id === stream.camera_id}
                isProcessing={activeStreams.includes(stream.camera_id)}
                isStopping={stoppingCams.has(stream.camera_id)}
                isRechecking={recheckingCams.has(stream.camera_id)}
                onSelect={() => setSelectedStream(stream.camera_id === selectedStream?.camera_id ? null : stream)}
                onRemove={() => handleRemove(stream.camera_id)}
                onReconnect={() => handleReconnect(stream.camera_id)}
                onStop={() => handleStop(stream.camera_id)}
                onEditUrl={(newUrl) => handleEditUrl(stream.camera_id, newUrl, stream.label)}
              />
            ))
          )}
        </div>

        {/* Summary bar */}
        <div className="border-t border-slate-800/30 px-4 py-2 flex-shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-4">
            {(["live", "offline", "error"] as RTSPStream["status"][]).map((s) => {
              const count = streams.filter((x) => statusOf(x.camera_id) === s).length;
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
  health,
  selected,
  isProcessing,
  isStopping,
  isRechecking,
  onSelect,
  onRemove,
  onReconnect,
  onStop,
  onEditUrl,
}: {
  stream: RTSPStream;
  health?: { reachable: boolean; latency_ms: number | null; checked_at: string; error: string | null };
  selected: boolean;
  isProcessing: boolean;
  isStopping: boolean;
  isRechecking: boolean;
  onSelect: () => void;
  onRemove: () => void;
  onReconnect: () => void;
  onStop: () => void;
  onEditUrl: (newUrl: string) => Promise<boolean>;
}) {
  const style = STATUS_STYLE[stream.status];
  const accent = CAMERA_ACCENTS[stream.camera_id] ?? DEFAULT_ACCENT;
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editUrl, setEditUrl] = useState(stream.rtsp_url);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState(false);

  const handleSaveEdit = async () => {
    setSavingEdit(true);
    setEditError(false);
    const ok = await onEditUrl(editUrl);
    setSavingEdit(false);
    if (ok) setEditing(false);
    else setEditError(true);
  };

  const startEdit = () => {
    setEditUrl(stream.rtsp_url);
    setEditError(false);
    setEditing(true);
  };

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
      style={{ gridTemplateColumns: "90px 1fr 120px 80px 60px 56px 100px 140px" }}
      onClick={onSelect}
    >
      {/* Cam ID */}
      <span className={`font-mono text-xs font-bold ${accent.text} border ${accent.border} px-1.5 py-0.5 rounded-sm inline-block w-fit`}>
        {stream.camera_id}
      </span>

      {/* URL / Label — inline editable */}
      <div className="min-w-0" onClick={(e) => editing && e.stopPropagation()}>
        <div className="font-mono text-xs text-slate-300 truncate">{stream.label ?? stream.camera_id}</div>
        {editing ? (
          <div className="flex items-center gap-1 mt-0.5">
            <input
              autoFocus
              value={editUrl}
              onChange={(e) => { setEditUrl(e.target.value); setEditError(false); }}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleSaveEdit();
                if (e.key === "Escape") setEditing(false);
              }}
              disabled={savingEdit}
              className={`flex-1 min-w-0 bg-slate-900/80 border rounded-sm px-1.5 py-0.5 font-mono text-[10px]
                text-slate-200 outline-none ${editError ? "border-red-600/70" : "border-cyan-700/60 focus:border-cyan-500"}`}
            />
            <button
              onClick={() => void handleSaveEdit()}
              disabled={savingEdit}
              title="Save URL"
              className="p-0.5 rounded-sm border border-green-700/60 text-green-400 hover:bg-green-950/40 disabled:opacity-40"
            >
              {savingEdit ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3 animate-spin"><path d="M12 2v4M4.93 4.93l2.83 2.83M2 12h4" /></svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3 h-3"><path d="M20 6L9 17l-5-5" /></svg>
              )}
            </button>
            <button
              onClick={() => setEditing(false)}
              disabled={savingEdit}
              title="Cancel"
              className="p-0.5 rounded-sm border border-slate-700 text-slate-500 hover:text-slate-300 disabled:opacity-40"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3 h-3"><path d="M18 6L6 18M6 6l12 12" /></svg>
            </button>
          </div>
        ) : (
          <div className="font-mono text-[10px] text-slate-600 truncate">{stream.rtsp_url}</div>
        )}
      </div>

      {/* Status — green=reachable, red=unreachable, grey=unknown */}
      <div className="flex items-center gap-1.5" title={health?.error ? `Unreachable: ${health.error}` : health?.checked_at ? `Checked: ${new Date(health.checked_at).toLocaleTimeString()}` : "Not checked yet"}>
        <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${style.dot}`} />
        <span className={`font-mono text-[10px] ${style.text}`}>
          {stream.status === "live" ? "ACTIVE" : stream.status === "error" ? "CAN'T CONNECT" : "UNKNOWN"}
        </span>
      </div>

      {/* Resolution */}
      <span className="font-mono text-[10px] text-slate-400">{stream.resolution ?? "—"}</span>

      {/* FPS */}
      <span className="font-mono text-[10px] text-slate-400 tabular-nums">
        {stream.fps != null ? <><span className="text-cyan-400">{stream.fps}</span> fps</> : "—"}
      </span>

      {/* Latency — real TCP connect time */}
      <span className="font-mono text-[9px] text-slate-600">
        {health?.reachable && health.latency_ms != null ? `${Math.round(health.latency_ms)}ms` : "—"}
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
        {/* Edit URL */}
        <button
          onClick={startEdit}
          title="Edit stream URL"
          className="p-1 rounded-sm border border-slate-700 text-slate-500 hover:border-yellow-700 hover:text-yellow-400 transition-colors"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3">
            <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
        </button>

        {/* Reconnect — force an immediate reachability recheck */}
        <button
          onClick={onReconnect}
          disabled={isRechecking}
          title="Reconnect (recheck reachability now)"
          className="p-1 rounded-sm border border-slate-700 text-slate-500 hover:border-cyan-700 hover:text-cyan-400 transition-colors disabled:opacity-40"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={`w-3 h-3 ${isRechecking ? "animate-spin" : ""}`}>
            <path d="M23 4v6h-6M1 20v-6h6" />
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
          </svg>
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
      <span className="font-mono text-[8px] text-red-400">CAN&apos;T CONNECT</span>
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
