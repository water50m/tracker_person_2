"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const NAV_ITEMS = [
  {
    href: "/dashboard",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    ),
    label: "DASHBOARD",
    sublabel: "LIVE MONITOR",
    accent: "cyan",
  },
  {
    href: "/investigation",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.35-4.35M11 8v6M8 11h6" />
      </svg>
    ),
    label: "INVESTIGATION",
    sublabel: "SEARCH & TRACE",
    accent: "pink",
  },
  {
    href: "/realtime",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
    ),
    label: "REALTIME",
    sublabel: "LIVE AI ANALYSIS",
    accent: "red",
  },
  {
    href: "/input-manager",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <path d="M15 10l4.553-2.277A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
      </svg>
    ),
    label: "INPUT MGR",
    sublabel: "VIDEO & STREAMS",
    accent: "yellow",
  },
  {
    href: "/search",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.35-4.35" />
        <path d="M11 7v4M9 9h4" />
      </svg>
    ),
    label: "SEARCH",
    sublabel: "QUERY & FILTER",
    accent: "green",
  },
  {
    href: "/camera-management",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <path d="M15 10l4.553-2.277A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
        <circle cx="8" cy="12" r="1.5" />
        <path d="M19 3l2 2-9 9-3 1 1-3 9-9z" opacity="0.4" />
      </svg>
    ),
    label: "CAM MGR",
    sublabel: "CAMERA MANAGER",
    accent: "violet",
  },
  {
    href: "/system",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
        <path d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
        <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
      </svg>
    ),
    label: "SYSTEM",
    sublabel: "SETTINGS & CONFIG",
    accent: "orange",
  },
];

const accentClasses: Record<string, { border: string; text: string; bg: string; glow: string }> = {
  cyan: {
    border: "border-cyan-500",
    text: "text-cyan-400",
    bg: "bg-cyan-500/10",
    glow: "shadow-[0_0_10px_rgba(0,245,255,0.3)]",
  },
  pink: {
    border: "border-pink-500",
    text: "text-pink-400",
    bg: "bg-pink-500/10",
    glow: "shadow-[0_0_10px_rgba(255,0,170,0.3)]",
  },
  yellow: {
    border: "border-yellow-500",
    text: "text-yellow-400",
    bg: "bg-yellow-500/10",
    glow: "shadow-[0_0_10px_rgba(255,190,0,0.3)]",
  },
  green: {
    border: "border-green-500",
    text: "text-green-400",
    bg: "bg-green-500/10",
    glow: "shadow-[0_0_10px_rgba(0,220,100,0.3)]",
  },
  violet: {
    border: "border-violet-500",
    text: "text-violet-400",
    bg: "bg-violet-500/10",
    glow: "shadow-[0_0_10px_rgba(139,92,246,0.3)]",
  },
  orange: {
    border: "border-orange-500",
    text: "text-orange-400",
    bg: "bg-orange-500/10",
    glow: "shadow-[0_0_10px_rgba(251,146,60,0.3)]",
  },
  red: {
    border: "border-red-500",
    text: "text-red-400",
    bg: "bg-red-500/10",
    glow: "shadow-[0_0_10px_rgba(255,50,50,0.3)]",
  },
};


export default function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={`
        relative flex flex-col h-screen z-20 transition-all duration-300
        ${collapsed ? "w-[60px]" : "w-[200px]"}
        bg-slate-950/90 border-r border-cyan-900/40
      `}
      style={{
        background:
          "linear-gradient(180deg, rgba(8,12,28,0.95) 0%, rgba(4,8,20,0.98) 100%)",
      }}
    >
      {/* Top glow line */}
      <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-cyan-500 to-transparent opacity-60" />

      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-cyan-900/30">
        {/* Icon */}
        <div className="relative flex-shrink-0">
          <div className="w-8 h-8 border border-cyan-500/60 rotate-45 flex items-center justify-center bg-cyan-950/60">
            <div className="w-2 h-2 bg-cyan-400 rotate-[-45deg]" />
          </div>
          <div className="absolute inset-0 bg-cyan-500/20 blur-sm rounded-full animate-pulse" />
        </div>
        {!collapsed && (
          <div>
            <div className="font-orbitron text-xs font-bold text-cyan-400 tracking-[0.25em]">
              NEXUS
            </div>
            <div className="font-mono text-[8px] text-slate-600 tracking-[0.3em]">
              EYE v2.4.1
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 space-y-1 px-2">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname.startsWith(item.href);
          const accent = accentClasses[item.accent];

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`
                group relative flex items-center gap-3 px-3 py-3 rounded-sm
                transition-all duration-200 overflow-hidden
                ${isActive
                  ? `${accent.bg} ${accent.border} border-l-2 ${accent.glow}`
                  : "border-l-2 border-transparent hover:bg-white/5"
                }
              `}
            >
              {/* Active left bar extra glow */}
              {isActive && (
                <div
                  className={`absolute left-0 top-0 bottom-0 w-0.5 blur-sm ${accent.text.replace("text-", "bg-")} opacity-80`}
                />
              )}

              {/* Corner scan line on hover */}
              <div className="absolute inset-0 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-white/10 to-transparent" />
              </div>

              <span className={`flex-shrink-0 ${isActive ? accent.text : "text-slate-600 group-hover:text-slate-400"} transition-colors`}>
                {item.icon}
              </span>

              {!collapsed && (
                <div className="min-w-0">
                  <div
                    className={`font-orbitron text-[10px] font-bold tracking-[0.15em] truncate ${isActive ? accent.text : "text-slate-500 group-hover:text-slate-300"
                      } transition-colors`}
                  >
                    {item.label}
                  </div>
                  <div className="font-mono text-[8px] text-slate-700 tracking-widest truncate">
                    {item.sublabel}
                  </div>
                </div>
              )}
            </Link>
          );
        })}
      </nav>

      {/* System status */}
      {!collapsed && (
        <div className="px-3 py-3 border-t border-cyan-900/20 space-y-1.5">
          <StatusRow label="AI ENGINE" status="online" />
          <StatusRow label="DATABASE" status="online" />
          <StatusRow label="STREAM 1" status="online" />
          <StatusRow label="STREAM 2" status="warn" />
        </div>
      )}

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full
          bg-slate-900 border border-cyan-900/60 flex items-center justify-center
          hover:border-cyan-500/60 transition-colors z-10"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          className={`w-3 h-3 text-cyan-600 transition-transform ${collapsed ? "rotate-180" : ""}`}
        >
          <path d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      {/* Bottom glow line */}
      <div className="absolute bottom-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-cyan-900 to-transparent" />
    </aside>
  );
}

function StatusRow({ label, status }: { label: string; status: "online" | "warn" | "offline" }) {
  const colors = {
    online: "bg-green-500",
    warn: "bg-yellow-500",
    offline: "bg-red-500",
  };

  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[8px] text-slate-700 tracking-wider">{label}</span>
      <div className="flex items-center gap-1">
        <div className={`w-1.5 h-1.5 rounded-full ${colors[status]} animate-pulse`} />
        <span
          className={`font-mono text-[7px] ${status === "online" ? "text-green-600" : status === "warn" ? "text-yellow-600" : "text-red-600"
            }`}
        >
          {status.toUpperCase()}
        </span>
      </div>
    </div>
  );
}
