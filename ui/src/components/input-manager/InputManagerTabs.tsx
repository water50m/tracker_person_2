"use client";

import React, { useState } from "react";
import UploadTab from "./UploadTab";
import RTSPTab from "./RTSPTab";
import YouTubeTab from "./YouTubeTab";
// React is imported for JSX and React.ReactNode type

// ─── Tab definitions ──────────────────────────────────────────

type TabId = "upload" | "rtsp" | "youtube";

interface Tab {
  id: TabId;
  label: string;
  sublabel: string;
  icon: React.ReactNode;
}

const TABS: Tab[] = [
  {
    id: "upload",
    label: "UPLOAD VIDEO",
    sublabel: "MP4 · AVI · MKV · MOV",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-4 h-4">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
      </svg>
    ),
  },
  {
    id: "rtsp",
    label: "RTSP STREAMS",
    sublabel: "LIVE CAMERA FEEDS",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-4 h-4">
        <path d="M15 10l4.553-2.277A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
        <circle cx="9" cy="12" r="1.5" fill="currentColor" className="animate-pulse" />
      </svg>
    ),
  },
  {
    id: "youtube" as TabId,
    label: "YOUTUBE",
    sublabel: "ANALYSE YT VIDEO",
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-red-500">
        <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 00-.79-.05 6.34 6.34 0 00-6.34 6.34 6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.33-6.34V8.69a8.18 8.18 0 004.77 1.52V6.75a4.85 4.85 0 01-1-.06z" />
      </svg>
    ),
  },
];

// ─── Component ────────────────────────────────────────────────

export default function InputManagerTabs() {
  const [activeTab, setActiveTab] = useState<TabId>("upload");

  return (
    <div className="h-full flex flex-col min-h-0">
      {/* ── Tab Bar ── */}
      <div className="flex items-end gap-1 flex-shrink-0 border-b border-yellow-900/30 pb-0">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                group relative flex items-center gap-2.5 px-5 py-3 transition-all duration-200
                ${isActive
                  ? "text-yellow-400"
                  : "text-slate-600 hover:text-slate-400"
                }
              `}
            >
              {/* Active bottom border */}
              {isActive && (
                <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-yellow-400 to-transparent" />
              )}

              {/* Hover underline */}
              {!isActive && (
                <div className="absolute bottom-0 left-0 right-0 h-[1px] bg-slate-700 opacity-0 group-hover:opacity-100 transition-opacity" />
              )}

              {/* Icon */}
              <span className={`transition-colors ${isActive ? "text-yellow-400" : "text-slate-700 group-hover:text-slate-500"}`}>
                {tab.icon}
              </span>

              {/* Labels */}
              <div className="text-left">
                <div className={`font-orbitron text-xs font-bold tracking-[0.15em] ${isActive ? "text-yellow-400" : ""}`}>
                  {tab.label}
                </div>
                <div className="font-mono text-[10px] text-slate-700 tracking-widest">
                  {tab.sublabel}
                </div>
              </div>

              {/* Active glow */}
              {isActive && (
                <div className="absolute inset-0 bg-yellow-950/20 pointer-events-none" />
              )}
            </button>
          );
        })}

        {/* Right: system info */}
        <div className="ml-auto flex items-center gap-4 pr-1 pb-3 self-end">
          <SystemInfoBadge label="QUEUE" value="3 JOBS" color="yellow" />
          <SystemInfoBadge label="PROCESSING" value="1 ACTIVE" color="cyan" />
          <SystemInfoBadge label="STORAGE" value="142 GB FREE" color="green" />
        </div>
      </div>

      {/* ── Tab Content ── */}
      <div className="flex-1 overflow-auto min-h-0 pt-4">
        {activeTab === "upload" && <UploadTab />}
        {activeTab === "rtsp" && <RTSPTab />}
        {activeTab === "youtube" && <YouTubeTab />}
      </div>
    </div>
  );
}

// ─── Sub-component ────────────────────────────────────────────

function SystemInfoBadge({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: "yellow" | "cyan" | "green";
}) {
  const colors = {
    yellow: "text-yellow-400",
    cyan: "text-cyan-400",
    green: "text-green-400",
  };
  return (
    <div className="text-right">
      <div className="font-mono text-[8px] text-slate-700 tracking-widest">{label}</div>
      <div className={`font-mono text-xs font-bold ${colors[color]}`}>{value}</div>
    </div>
  );
}