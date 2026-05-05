"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useInvestigation } from "./InvestigationContext";
import type { TraceResponse, TraceEvent, SearchResult } from "@/types";

// ─── Helpers ─────────────────────────────────────────────────

function formatFull(iso: string) {
  const d = new Date(iso);
  return {
    date: d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase(),
    time: d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
  };
}

function elapsed(from: string, to: string): string {
  const sec = Math.floor((new Date(to).getTime() - new Date(from).getTime()) / 1000);
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
}

const CAMERA_ACCENT: Record<string, { text: string; border: string; dot: string }> = {
  "CAM-01": { text: "text-cyan-400",   border: "border-cyan-800",  dot: "#00f5ff" },
  "CAM-02": { text: "text-pink-400",   border: "border-pink-900",  dot: "#ff00aa" },
  "CAM-03": { text: "text-yellow-400", border: "border-yellow-900",dot: "#ffd700" },
  "CAM-04": { text: "text-purple-400", border: "border-purple-900",dot: "#a855f7" },
};
const DEFAULT_ACCENT = { text: "text-slate-400", border: "border-slate-700", dot: "#94a3b8" };

// ─── Component ───────────────────────────────────────────────

export default function TraceModal() {
  const { state, closeTrace } = useInvestigation();
  const { traceTarget } = state;

  const [traceData, setTraceData] = useState<TraceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<TraceEvent | null>(null);
  const [showColorDetails, setShowColorDetails] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  // Fetch trace
  useEffect(() => {
    if (!traceTarget) {
      setTraceData(null);
      setSelectedEvent(null);
      return;
    }

    setLoading(true);
    setError(false);
    setSelectedEvent(null);

    fetch(`/api/trace/${encodeURIComponent(traceTarget.id)}`)
      .then((r) => {
        if (!r.ok) throw new Error("Not found");
        return r.json();
      })
      .then((data: TraceResponse) => {
        const detections = Array.isArray(data.detections) ? data.detections : [];
        setTraceData({ ...data, detections });
        setSelectedEvent(detections.length > 0 ? detections[0] : null);
      })
      .catch(() => {
        setError(true);
        setTraceData(null);
        setSelectedEvent(null);
      })
      .finally(() => setLoading(false));
  }, [traceTarget]);

  // Keyboard close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") closeTrace(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [closeTrace]);

  // Backdrop click close
  const handleOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === overlayRef.current) closeTrace();
    },
    [closeTrace]
  );

  // Export
  const handleExport = useCallback(() => {
    if (!traceData || !traceTarget) return;
    const report = {
      exported_at: new Date().toISOString(),
      person_id: traceData.person_id,
      attributes: traceData.attributes,
      cameras_visited: traceData.cameras,
      total_detections: traceData.detections.length,
      timeline: traceData.detections.map((d) => ({
        camera: d.camera_name,
        time: d.timestamp,
        confidence: d.confidence,
      })),
    };
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trace_${traceData.person_id}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [traceData, traceTarget]);

  if (!traceTarget) return null;
  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm"
      onClick={handleOverlayClick}
      style={{ animation: "fade-in 0.2s ease-out" }}
    >
      <div
        className="relative w-full max-w-3xl max-h-[90vh] hud-panel flex flex-col overflow-hidden"
        style={{ animation: "slide-in-up 0.3s ease-out" }}
      >
        {/* Top accent line */}
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-pink-500 to-transparent" />

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/60 flex-shrink-0">
          <div>
            <h2 className="font-orbitron text-sm font-bold text-pink-400 tracking-[0.2em]">
              TRACE ANALYSIS
            </h2>
            <p className="font-mono text-[9px] text-slate-600 mt-0.5 tracking-widest">
              ID: {traceTarget.id} · {traceTarget.clothing_class} · {traceTarget.color}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowColorDetails(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-sm border border-cyan-700/60
                bg-cyan-950/30 font-mono text-[9px] text-cyan-300 hover:bg-cyan-900/40 transition-colors"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3">
                <path d="M12 2a10 10 0 100 20 10 10 0 000-20zm0 4v6l4 2" />
              </svg>
              COLOR DETAILS
            </button>
            <button
              onClick={handleExport}
              disabled={!traceData}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-sm border border-yellow-700/60
                bg-yellow-950/30 font-mono text-[9px] text-yellow-400 hover:bg-yellow-900/40
                transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
              </svg>
              EXPORT
            </button>
            <button
              onClick={closeTrace}
              className="p-1.5 rounded-sm border border-slate-700 text-slate-500 hover:border-slate-600 hover:text-slate-300 transition-colors"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* ── Body ── */}
        <div className="flex-1 overflow-hidden flex min-h-0">
          {loading ? (
            <LoadingState />
          ) : error ? (
            <ErrorState />
          ) : traceData ? (
            <ModalBody
              trace={traceData}
              traceTarget={traceTarget}
              selectedEvent={selectedEvent}
              onSelectEvent={setSelectedEvent}
              showColorDetails={showColorDetails}
              onColorDetailsClose={() => setShowColorDetails(false)}
            />
          ) : null}
        </div>
      </div>

    </div>
  );
}

// ─── Modal Body ───────────────────────────────────────────────

function ModalBody({
  trace,
  traceTarget,
  selectedEvent,
  onSelectEvent,
  showColorDetails,
  onColorDetailsClose,
}: {
  trace: TraceResponse;
  traceTarget: SearchResult;
  selectedEvent: TraceEvent | null;
  onSelectEvent: (e: TraceEvent) => void;
  showColorDetails: boolean;
  onColorDetailsClose: () => void;
}) {
  const hasDetections = Array.isArray(trace.detections) && trace.detections.length > 0;
  const totalDuration =
    hasDetections && trace.detections.length >= 2
      ? elapsed(
          trace.detections[0].timestamp,
          trace.detections[trace.detections.length - 1].timestamp
        )
      : null;

  const firstDetection = hasDetections ? trace.detections[0] : null;
  const lastDetection = hasDetections ? trace.detections[trace.detections.length - 1] : null;

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* ── Left: Enlarged image + attributes ── */}
      <div className="w-52 flex-shrink-0 flex flex-col border-r border-slate-800/60">
        {/* Image */}
        <div className="relative flex-shrink-0" style={{ height: 320 }}>
          {traceTarget?.thumbnail_url ? (
            <Image
              src={traceTarget.thumbnail_url}
              alt="Target"
              fill
              className="object-cover"
              unoptimized
            />
          ) : (
            <div className="absolute inset-0 bg-slate-900 flex items-center justify-center">
              <span className="font-mono text-[9px] text-slate-700">NO IMAGE</span>
            </div>
          )}
          {/* Neon frame */}
          <div className="absolute inset-0 pointer-events-none border border-pink-500/20" />
          <div className="absolute top-1.5 left-1.5 w-3 h-3 border-t-2 border-l-2 border-pink-400/60" />
          <div className="absolute bottom-1.5 right-1.5 w-3 h-3 border-b-2 border-r-2 border-pink-400/60" />
          {/* Scanlines */}
          <div className="absolute inset-0 pointer-events-none"
            style={{ background: "repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,0,0,0.08) 3px,rgba(0,0,0,0.08) 4px)" }} />
          {/* Action buttons */}
          <div className="absolute bottom-2 left-2 right-2 flex gap-1">
            <button 
              className="flex-1 py-1.5 bg-cyan-950/60 border border-cyan-700/60 rounded-sm
                font-mono text-[8px] text-cyan-400 hover:bg-cyan-900/60 transition-colors"
            >
              TRACE
            </button>
            <button 
              onClick={() => {
                // Get video info from traceTarget and navigate to search page
                const videoId = traceTarget?.video_id;
                const timeOffset = traceTarget?.video_time_offset;
                
                if (videoId) {
                  const params = new URLSearchParams({
                    video: videoId,
                    time: timeOffset?.toString() || "0"
                  });
                  window.open(`/search?${params.toString()}`, '_blank');
                } else {
                  alert('No video available for this detection');
                }
              }}
              className="flex-1 py-1.5 bg-purple-950/60 border border-purple-700/60 rounded-sm
                font-mono text-[8px] text-purple-400 hover:bg-purple-900/60 transition-colors"
            >
              VIDEO
            </button>
          </div>
        </div>

        {/* Attributes */}
        <div className="flex-1 p-3 space-y-2 overflow-y-auto">
          <div className="font-mono text-[8px] text-slate-600 tracking-[0.2em] uppercase mb-2">ATTRIBUTES</div>
          {Object.entries(trace.attributes).map(([key, val]) => (
            <div key={key} className="flex justify-between gap-2">
              <span className="font-mono text-[8px] text-slate-600 uppercase">{key}</span>
              <span className="font-mono text-[9px] text-slate-300">{val}</span>
            </div>
          ))}

          <div className="pt-2 border-t border-slate-800/60 space-y-1">
            <div className="flex justify-between">
              <span className="font-mono text-[8px] text-slate-600">CAMERAS</span>
              <span className="font-mono text-[9px] text-cyan-400">{trace.cameras.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="font-mono text-[8px] text-slate-600">SIGHTINGS</span>
              <span className="font-mono text-[9px] text-cyan-400">{trace.detections.length}</span>
            </div>
            {totalDuration && (
              <div className="flex justify-between">
                <span className="font-mono text-[8px] text-slate-600">DURATION</span>
                <span className="font-mono text-[9px] text-yellow-400">{totalDuration}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Right: Journey Timeline + Color Sidebar ── */}
      <div className="flex-1 p-4 min-h-0 overflow-hidden">
        <div className="flex gap-4 h-full min-h-0">
          <div className="flex-1 overflow-y-auto">
            <div className="font-mono text-[8px] text-slate-600 tracking-[0.2em] mb-4">
              JOURNEY TIMELINE · {trace.detections.length} SIGHTINGS
            </div>

            {/* Vertical timeline */}
            <div className="relative">
              {/* Vertical line */}
              <div className="absolute left-4 top-0 bottom-0 w-px bg-gradient-to-b from-pink-500/60 via-cyan-500/30 to-transparent" />

              {!hasDetections ? (
                <div className="py-8 text-center text-slate-500 font-mono text-sm">No sightings available for this trace.</div>
              ) : (
                <div className="space-y-1">
                  {trace.detections.map((det, i) => {
                    const accent = CAMERA_ACCENT[det.camera_id] ?? DEFAULT_ACCENT;
                    const isSelected = selectedEvent?.id === det.id;
                    const isFirst = i === 0;
                    const isLast = i === trace.detections.length - 1;
                    const { date, time } = formatFull(det.timestamp);
                    const gap = i > 0 ? elapsed(trace.detections[i - 1].timestamp, det.timestamp) : null;

                    return (
                      <div key={det.id}>
                        {gap && (
                          <div className="flex items-center gap-2 py-1 pl-12">
                            <div className="flex-1 h-px border-t border-dashed border-slate-800" />
                            <span className="font-mono text-[7px] text-slate-700 flex-shrink-0">+{gap}</span>
                            <div className="flex-1 h-px border-t border-dashed border-slate-800" />
                          </div>
                        )}

                        <button
                          onClick={() => onSelectEvent(det)}
                          className={`relative flex gap-3 items-start w-full text-left rounded-sm p-2 pl-10 transition-all duration-150 ${isSelected ? `bg-slate-900/60 border border-slate-700/60` : "hover:bg-slate-900/30 border border-transparent"}`}
                        >
                          <div className="absolute left-3 top-3.5 w-3 h-3 rounded-full border-2 flex-shrink-0 z-10" style={{ background: isFirst || isLast ? accent.dot : "transparent", borderColor: accent.dot, boxShadow: isSelected ? `0 0 8px ${accent.dot}80` : "none" }} />

                          <div className="relative w-14 h-20 flex-shrink-0 rounded-sm overflow-hidden border border-slate-700/60">
                            {det.thumbnail_url && (
                              <Image src={det.thumbnail_url} alt={det.camera_name} fill className="object-cover opacity-80" unoptimized />
                            )}
                          </div>

                          <div className="flex-1 min-w-0 pt-0.5">
                            <div className="flex items-center gap-2 mb-1">
                              {(isFirst || isLast) && (
                                <span className={`font-mono text-[7px] px-1.5 py-0.5 rounded-sm border ${isFirst ? "border-green-800 text-green-500 bg-green-950/40" : "border-red-900 text-red-500 bg-red-950/40"}`}>
                                  {isFirst ? "ENTRY" : "LAST SEEN"}
                                </span>
                              )}
                              <span className={`font-mono text-[9px] font-bold ${accent.text}`}>{det.camera_name}</span>
                              <span className={`font-mono text-[7px] border px-1 rounded-sm ${accent.border} ${accent.text} opacity-60`}>{det.camera_id}</span>
                            </div>
                            <div className="font-mono text-[10px] text-slate-300 tabular-nums">{time}</div>
                            <div className="font-mono text-[8px] text-slate-600">{date}</div>
                            <div className="flex items-center gap-3 mt-1.5">
                              <div className="font-mono text-[8px] text-slate-500">CONF <span className="text-cyan-400">{Math.round(det.confidence * 100)}%</span></div>
                              {det.bounding_box && <div className="font-mono text-[7px] text-slate-700">BOX [{Math.round(det.bounding_box.x * 100)},{Math.round(det.bounding_box.y * 100)}]</div>}
                            </div>
                            <div className="mt-1.5 h-0.5 bg-slate-800 rounded-full overflow-hidden w-24">
                              <div className="h-full rounded-full transition-all" style={{ width: `${det.confidence * 100}%`, background: det.confidence >= 0.9 ? "#39ff14" : det.confidence >= 0.75 ? "#00f5ff" : "#ffd700" }} />
                            </div>
                          </div>
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="mt-4 ml-10 flex items-center gap-3">
                <div className="h-px flex-1 bg-gradient-to-r from-slate-700 to-transparent" />
                <span className="font-mono text-[7px] text-slate-700 tracking-widest">END OF TRACE</span>
              </div>
            </div>
          </div>

          {showColorDetails && (
            <div className="w-80 flex-shrink-0 border-l border-slate-800/60 pl-4">
              <div className="p-3 bg-slate-900 rounded-sm border border-cyan-700/40 h-full overflow-y-auto">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-orbitron text-xs text-cyan-300 tracking-widest">COLOR DETAILS</h3>
                  <button onClick={() => onColorDetailsClose()} className="text-slate-400 hover:text-white text-xs">✕</button>
                </div>
                <div className="space-y-2">
                  <div className="font-mono text-[9px] text-slate-400">Person:</div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="p-2 bg-slate-800/50 border border-slate-700 rounded-sm">
                      <div className="text-[11px] text-slate-500">Clothing</div>
                      <div className="font-mono text-sm text-cyan-300 font-bold">{selectedEvent?.clothing_class || trace.attributes?.value || "Unknown"}</div>
                    </div>
                    <div className="p-2 bg-slate-800/50 border border-slate-700 rounded-sm">
                      <div className="text-[11px] text-slate-500">Color</div>
                      <div className="font-mono text-sm text-purple-300 font-bold">{selectedEvent?.color || traceTarget?.color || "Unknown"}</div>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-slate-800">
                    <div className="font-mono text-[8px] text-slate-500 uppercase tracking-widest mb-1">Color Profile</div>
                    {selectedEvent?.color_profile ? (
                      <div className="space-y-1">
                        {Object.entries(selectedEvent.color_profile)
                          .sort((a, b) => b[1] - a[1])
                          .map(([color, pct]) => (
                            <div key={color} className="flex justify-between items-center">
                              <span className="font-mono text-[9px] text-slate-300 uppercase">{color}</span>
                              <span className="font-mono text-[9px] text-cyan-300">{pct.toFixed(1)}%</span>
                            </div>
                          ))}
                      </div>
                    ) : (
                      <div className="font-mono text-[9px] text-slate-400">No color profile available.</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ColorDetailsModal({
  traceData,
  selectedEvent,
  onClose,
}: {
  traceData: TraceResponse;
  selectedEvent: TraceEvent | null;
  onClose: () => void;
}) {
  const chartColors = selectedEvent?.color_profile ? selectedEvent.color_profile : null;

  return (
    <div className="fixed inset-0 z-60 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
      <div className="w-[min(512px,95vw)] bg-slate-900 border border-cyan-700/60 rounded-md p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="font-orbitron text-xs text-cyan-300 tracking-widest">COLOR INSPECT</h3>
            <p className="font-mono text-[8px] text-slate-500">ID: {traceData.person_id}</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-sm"
          >×</button>
        </div>

        <div className="space-y-2">
          <div className="font-mono text-[9px] text-slate-400">Detected Person Color</div>
          <div className="flex gap-2 flex-wrap">
            <span className="px-2 py-1 rounded-sm border border-cyan-700 text-cyan-300 text-[10px]">{traceData.attributes?.color || traceData.cameras?.[0] || "N/A"}</span>
            <span className="px-2 py-1 rounded-sm border border-pink-700 text-pink-300 text-[10px]">{selectedEvent?.color || traceData.detections[0]?.color || "Unknown"}</span>
            <span className="px-2 py-1 rounded-sm border border-green-700 text-green-300 text-[10px]">{selectedEvent?.clothing_class || traceData.detections[0]?.clothing_class || "Unknown"}</span>
          </div>

          <div className="pt-2 border-t border-slate-800">
            <div className="font-mono text-[8px] text-slate-500 uppercase tracking-widest mb-1">Color Profile (frame-level)</div>
            {!chartColors && (
              <div className="font-mono text-[9px] text-slate-400">No color profile available for selected frame.</div>
            )}
            {chartColors && (
              <div className="space-y-1">
                {Object.entries(chartColors)
                  .sort((a, b) => b[1] - a[1])
                  .map(([color, pct]) => (
                    <div key={color} className="flex justify-between items-center">
                      <span className="font-mono text-[9px] text-slate-300 uppercase">{color}</span>
                      <span className="font-mono text-[9px] text-cyan-300">{pct.toFixed(1)}%</span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Loading / Error states ───────────────────────────────────

function LoadingState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4">
      <div className="relative w-16 h-16">
        <div className="absolute inset-0 border-2 border-pink-500/30 rounded-full animate-ping" />
        <div className="absolute inset-2 border border-pink-500/60 rounded-full" />
        <div className="absolute inset-0 flex items-center justify-center">
          <svg viewBox="0 0 24 24" fill="none" stroke="#ff00aa" strokeWidth={1.5} className="w-6 h-6 animate-spin" style={{ animationDuration: "2s" }}>
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4" />
          </svg>
        </div>
      </div>
      <p className="font-mono text-[10px] text-pink-500 tracking-[0.2em]">TRACING SUBJECT</p>
      <div className="progress-bar w-32" />
    </div>
  );
}

function ErrorState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-10 h-10 text-red-700">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
        <path d="M12 9v4M12 17h.01" />
      </svg>
      <p className="font-mono text-[10px] text-red-600 tracking-widest">TRACE DATA UNAVAILABLE</p>
    </div>
  );
}