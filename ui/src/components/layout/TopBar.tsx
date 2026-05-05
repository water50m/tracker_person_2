"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

const PAGE_TITLES: Record<string, { label: string; color: string }> = {
  "/dashboard": { label: "// LIVE MONITOR", color: "text-cyan-500" },
  "/investigation": { label: "// SEARCH & TRACE", color: "text-pink-500" },
  "/input-manager": { label: "// INPUT MANAGER", color: "text-yellow-500" },
};

export default function TopBar() {
  const pathname = usePathname();
  const [time, setTime] = useState<Date | null>(null);

  useEffect(() => {
    setTime(new Date());
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const page = PAGE_TITLES[pathname] ?? { label: "// SYSTEM", color: "text-slate-400" };

  const formatTime = (d: Date) =>
    d.toTimeString().slice(0, 8);

  const formatDate = (d: Date) =>
    d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
      .toUpperCase()
      .replace(/ /g, "-");

  return (
    <header className="flex-shrink-0 flex items-center justify-between px-5 py-2.5
      border-b border-cyan-900/30 bg-slate-950/70 backdrop-blur-sm"
    >
      {/* Left: breadcrumb */}
      <div className="flex items-center gap-3">
        <span className="font-orbitron text-[10px] font-bold text-slate-600 tracking-[0.3em] uppercase">
          NEXUS-EYE
        </span>
        <span className="text-slate-700">›</span>
        <span className={`font-mono text-[11px] ${page.color} tracking-widest`}>
          {page.label}
        </span>
      </div>

      {/* Center: ticker */}
      <div className="hidden md:flex items-center gap-1 font-mono text-[9px] text-slate-700 tracking-widest overflow-hidden max-w-md">
        <TickerTape />
      </div>

      {/* Right: clock + indicators */}
      <div className="flex items-center gap-4">
        {/* Network indicator */}
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse" />
          <span className="font-mono text-[9px] text-cyan-700 tracking-wider">LIVE</span>
        </div>

        {/* Clock */}
        {time && (
          <div className="text-right">
            <div className="font-mono text-xs text-cyan-400 tracking-[0.2em] tabular-nums">
              {formatTime(time)}
            </div>
            <div className="font-mono text-[8px] text-slate-600 tracking-widest">
              {formatDate(time)}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}

function TickerTape() {
  const messages = [
    "SYSTEM NOMINAL",
    "AI ENGINE: ACTIVE",
    "DETECTIONS TODAY: 247",
    "ATTRIBUTE SEARCH: ENABLED",
    "CAMERAS ONLINE: 4/6",
    "LAST SYNC: OK",
  ];

  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setIndex((i) => (i + 1) % messages.length);
        setVisible(true);
      }, 300);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <span
      className={`transition-opacity duration-300 ${visible ? "opacity-100" : "opacity-0"}`}
    >
      <span className="text-cyan-900 mr-2">▸</span>
      {messages[index]}
    </span>
  );
}
