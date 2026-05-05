"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Image from "next/image";

// ─── Types ────────────────────────────────────────────────────

interface FeedEvent {
  id: string;
  camera_id: string;
  timestamp: string;
  clothing: string;
  confidence: number;
  thumbnail_url: string;
  isNew?: boolean;
}

// ─── Seed data / Initial State ────────────────────────────────

const SEED_EVENTS: FeedEvent[] = [];

// ─── Helpers ──────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

function confidenceColor(c: number): string {
  if (c >= 0.9) return "text-green-400";
  if (c >= 0.75) return "text-cyan-400";
  if (c >= 0.6) return "text-yellow-400";
  return "text-red-400";
}

function confidenceBg(c: number): string {
  if (c >= 0.9) return "bg-green-500/15 border-green-500/30";
  if (c >= 0.75) return "bg-cyan-500/15 border-cyan-500/30";
  return "bg-yellow-500/10 border-yellow-500/20";
}

const CAMERA_ACCENT: Record<string, string> = {
  "CAM-01": "text-cyan-400 border-cyan-800",
  "CAM-02": "text-pink-400 border-pink-900",
  "CAM-03": "text-yellow-400 border-yellow-900",
  "CAM-04": "text-purple-400 border-purple-900",
};

// ─── Component ────────────────────────────────────────────────

export default function EventFeed() {
  const [events, setEvents] = useState<FeedEvent[]>(SEED_EVENTS);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<string>("ALL");
  const [totalToday, setTotalToday] = useState(0);
  const [connectionStatus, setConnectionStatus] = useState<"connecting" | "live" | "error">("connecting");
  const listRef = useRef<HTMLDivElement>(null);
  const pendingRef = useRef<FeedEvent[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Poll for today's detection count since SSE might not send it immediately
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch("/api/stats/hourly");
        if (res.ok) {
          const data = await res.json();
          // sum total detections for today
          const total = data.reduce((acc: number, cur: any) => acc + (cur.count || 0), 0);
          setTotalToday(total);
        }
      } catch (e) {
        // ignore
      }
    };
    fetchStats();
    const t = setInterval(fetchStats, 60000); // refresh every minute
    return () => clearInterval(t);
  }, []);

  // ── Polling fallback for live events until SSE is robust ──
  // The SSE implementation needs redis/rabbitmq in backend to broadcast events from background workers.
  // Polling /api/detections efficiently acts as the real-time feed for now.
  const lastEventIdRef = useRef<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    // Simulate SSE connection state
    setConnectionStatus("live");

    const fetchLatestEvents = async () => {
      try {
        const res = await fetch("/api/detections?limit=10");
        if (!res.ok) return;
        const data = await res.json();

        if (!isMounted) return;

        const MINIO_BASE = process.env.NEXT_PUBLIC_MINIO_URL ?? "http://localhost:9000";

        // Convert API response to FeedEvent
        const newEvents: FeedEvent[] = data.map((det: any) => ({
          id: String(det.id),
          camera_id: det.camera_id,
          timestamp: det.timestamp,
          clothing: det.class_name,
          confidence: det.confidence || 0.90, // mock confidence since backend does not persist it yet
          thumbnail_url: det.image_url ? det.image_url : `${MINIO_BASE}/${det.image_path}`,
          isNew: true
        }));

        setEvents((prev) => {
          // Find which ones are actually new
          const existingIds = new Set(prev.map(e => e.id));
          const trulyNew = newEvents.filter(e => !existingIds.has(e.id));

          if (trulyNew.length === 0) return prev;

          if (paused) {
            // Add to pending if paused, avoid duplicates
            const pendingIds = new Set(pendingRef.current.map(e => e.id));
            const newPending = trulyNew.filter(e => !pendingIds.has(e.id));
            pendingRef.current = [...newPending, ...pendingRef.current];
            return prev;
          } else {
            const updated = [...trulyNew, ...prev].slice(0, 80);
            return updated;
          }
        });

      } catch (err) {
        if (isMounted) setConnectionStatus("error");
      }
    };

    fetchLatestEvents();
    const t = setInterval(fetchLatestEvents, 5000); // 5s refresh for event feed

    return () => {
      isMounted = false;
      clearInterval(t);
    };
  }, [paused]);

  // ── Add event to top of list ──
  const addEvent = useCallback((event: FeedEvent) => {
    setEvents((prev) => {
      const updated = [event, ...prev].slice(0, 80); // cap at 80
      return updated;
    });
    // Auto-scroll to top if near top
    if (listRef.current && listRef.current.scrollTop < 80) {
      setTimeout(() => {
        listRef.current?.scrollTo({ top: 0, behavior: "smooth" });
      }, 50);
    }
  }, []);

  // ── Resume: flush pending ──
  const handleResume = () => {
    setPaused(false);
    const pending = pendingRef.current.splice(0);
    setEvents((prev) => [...pending, ...prev].slice(0, 80));
  };

  // ── Remove "isNew" flag after animation ──
  useEffect(() => {
    // Performance fix: Prevent infinite mapping loop if there's nothing to update
    const hasNew = events.some((e) => e.isNew);
    if (!hasNew) return;

    const t = setTimeout(() => {
      setEvents((prev) =>
        prev.map((e) => (e.isNew ? { ...e, isNew: false } : e))
      );
    }, 600);
    return () => clearTimeout(t);
  }, [events]);

  // ── Filtered events ──
  const filtered = filter === "ALL"
    ? events
    : events.filter((e) => e.camera_id === filter);

  const cameras = Array.from(new Set(events.map((e) => e.camera_id))).sort();

  return (
    <div className="hud-panel flex flex-col min-h-0 overflow-hidden">
      {/* ── Header ── */}
      <div className="px-3 py-2 border-b border-cyan-900/30 flex-shrink-0">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="font-orbitron text-[10px] font-bold text-slate-300 tracking-[0.2em]">
              EVENT FEED
            </span>
            {/* Connection badge */}
            <ConnectionBadge status={connectionStatus} />
          </div>
          {/* Pause/Resume */}
          <button
            onClick={() => paused ? handleResume() : setPaused(true)}
            className={`
              flex items-center gap-1 px-2 py-0.5 rounded-sm border font-mono text-[9px] tracking-wider transition-all
              ${paused
                ? "border-yellow-600/60 text-yellow-400 bg-yellow-950/30 hover:bg-yellow-950/50"
                : "border-slate-700 text-slate-600 hover:border-slate-600 hover:text-slate-400"
              }
            `}
          >
            {paused ? (
              <>
                <svg viewBox="0 0 24 24" fill="currentColor" className="w-2.5 h-2.5"><path d="M8 5v14l11-7z" /></svg>
                RESUME {pendingRef.current.length > 0 && `(+${pendingRef.current.length})`}
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="currentColor" className="w-2.5 h-2.5"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>
                PAUSE
              </>
            )}
          </button>
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-3">
          <div className="flex-1 flex items-center justify-between">
            <span className="font-mono text-[8px] text-slate-600">TODAY</span>
            <span className="font-mono text-[10px] text-cyan-400 tabular-nums">{totalToday.toLocaleString()}</span>
          </div>
          <div className="w-px h-3 bg-slate-800" />
          <div className="flex-1 flex items-center justify-between">
            <span className="font-mono text-[8px] text-slate-600">QUEUE</span>
            <span className="font-mono text-[10px] text-slate-400 tabular-nums">{events.length}</span>
          </div>
        </div>

        {/* Camera filter chips */}
        <div className="flex items-center gap-1 mt-2 overflow-x-auto pb-0.5">
          <FilterChip label="ALL" active={filter === "ALL"} onClick={() => setFilter("ALL")} />
          {cameras.map((cam) => (
            <FilterChip
              key={cam}
              label={cam}
              active={filter === cam}
              onClick={() => setFilter(cam)}
              accent={CAMERA_ACCENT[cam]}
            />
          ))}
        </div>
      </div>

      {/* ── Pause overlay banner ── */}
      {paused && (
        <div className="flex-shrink-0 bg-yellow-950/40 border-b border-yellow-800/40 px-3 py-1.5 flex items-center gap-2">
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-3 h-3 text-yellow-500 flex-shrink-0">
            <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
          </svg>
          <span className="font-mono text-[9px] text-yellow-500 tracking-wider">
            FEED PAUSED · {pendingRef.current.length} NEW EVENTS BUFFERED
          </span>
        </div>
      )}

      {/* ── Event list ── */}
      <div
        ref={listRef}
        className="flex-1 overflow-y-auto space-y-1 p-2 min-h-0"
      >
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-8 h-8 text-slate-800">
              <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
            </svg>
            <p className="font-mono text-[9px] text-slate-700 tracking-wider">NO EVENTS DETECTED</p>
          </div>
        ) : (
          filtered.map((event) => (
            <EventCard key={event.id} event={event} />
          ))
        )}
      </div>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────

function EventCard({ event }: { event: FeedEvent }) {
  const [expanded, setExpanded] = useState(false);
  const accent = CAMERA_ACCENT[event.camera_id] ?? "text-slate-400 border-slate-800";

  return (
    <div
      className={`
        group relative flex gap-2 p-2 rounded-sm border cursor-pointer
        transition-all duration-200 select-none
        ${event.isNew
          ? "animate-slide-in-right border-cyan-500/30 bg-cyan-950/20"
          : "border-slate-800/60 bg-slate-900/30 hover:bg-slate-900/60 hover:border-slate-700/60"
        }
      `}
      onClick={() => setExpanded((s) => !s)}
    >
      {/* New pulse dot */}
      {event.isNew && (
        <div className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />
      )}

      {/* Thumbnail */}
      <div className="relative w-10 h-14 flex-shrink-0 bg-slate-800/60 rounded-sm overflow-hidden border border-slate-700/40">
        <Image
          src={event.thumbnail_url}
          alt={event.clothing}
          fill
          className="object-cover"
          unoptimized
        />
        {/* Scanline */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: "repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,0,0,0.12) 3px,rgba(0,0,0,0.12) 4px)",
          }}
        />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Clothing label */}
        <div className="font-mono text-[10px] text-slate-200 truncate leading-tight">
          {event.clothing}
        </div>

        {/* Camera + confidence */}
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className={`font-mono text-[8px] border px-1 rounded-sm ${accent}`}>
            {event.camera_id}
          </span>
          <span className={`font-mono text-[9px] font-bold ${confidenceColor(event.confidence)}`}>
            {Math.round(event.confidence * 100)}%
          </span>
        </div>

        {/* Time */}
        <div className="font-mono text-[8px] text-slate-600 mt-0.5">
          <RelativeTime iso={event.timestamp} />
        </div>

        {/* Expanded detail */}
        {expanded && (
          <div className={`mt-1.5 pt-1.5 border-t border-slate-800 space-y-0.5`}>
            <div className="font-mono text-[8px] text-slate-500">
              TIME: <span className="text-slate-400">{new Date(event.timestamp).toLocaleTimeString()}</span>
            </div>
            <div className="font-mono text-[8px] text-slate-500">
              ID: <span className="text-slate-500">{event.id}</span>
            </div>
            <div className={`inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded-sm border text-[8px] font-mono ${confidenceBg(event.confidence)} ${confidenceColor(event.confidence)}`}>
              CONF {Math.round(event.confidence * 100)}%
            </div>
          </div>
        )}
      </div>

      {/* Expand icon */}
      <div className="flex-shrink-0 self-center opacity-0 group-hover:opacity-100 transition-opacity">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          className={`w-3 h-3 text-slate-600 transition-transform ${expanded ? "rotate-180" : ""}`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </div>
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
  accent,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  accent?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`
        flex-shrink-0 px-2 py-0.5 rounded-sm border font-mono text-[8px] tracking-wider transition-all
        ${active
          ? "border-cyan-500/60 bg-cyan-950/40 text-cyan-400"
          : `border-slate-800 text-slate-600 hover:text-slate-400 hover:border-slate-700 ${accent ?? ""}`
        }
      `}
    >
      {label}
    </button>
  );
}

function ConnectionBadge({ status }: { status: "connecting" | "live" | "error" }) {
  if (status === "live") {
    return (
      <div className="flex items-center gap-1">
        <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
        <span className="font-mono text-[8px] text-green-600 tracking-wider">LIVE</span>
      </div>
    );
  }
  if (status === "connecting") {
    return (
      <div className="flex items-center gap-1">
        <div className="w-1.5 h-1.5 rounded-full bg-yellow-500 animate-pulse" />
        <span className="font-mono text-[8px] text-yellow-600 tracking-wider">CONNECTING</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1">
      <div className="w-1.5 h-1.5 rounded-full bg-red-500" />
      <span className="font-mono text-[8px] text-red-600 tracking-wider">RECONNECTING</span>
    </div>
  );
}

function RelativeTime({ iso }: { iso: string }) {
  const [label, setLabel] = useState(relativeTime(iso));
  useEffect(() => {
    const t = setInterval(() => setLabel(relativeTime(iso)), 5000);
    return () => clearInterval(t);
  }, [iso]);
  return <>{label}</>;
}