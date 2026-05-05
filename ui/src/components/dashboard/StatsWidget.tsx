"use client";

import React, { useEffect, useRef, useState } from "react";

// ─── Types ────────────────────────────────────────────────────

interface HourlyPoint {
  hour: string;
  count: number;
}

interface StatCard {
  label: string;
  value: number;
  suffix?: string;
  delta?: number;
  accent: "cyan" | "green" | "yellow" | "pink";
  icon: React.ReactNode;
}

// ─── Sparkline Canvas ─────────────────────────────────────────

function Sparkline({
  data,
  width = 300,
  height = 52,
  color = "#00f5ff",
  fillOpacity = 0.15,
}: {
  data: HourlyPoint[];
  width?: number;
  height?: number;
  color?: string;
  fillOpacity?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.length === 0) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const W = rect.width || width;
    const H = rect.height || height;

    canvas.width = W * dpr;
    canvas.height = H * dpr;
    const ctx = canvas.getContext("2d")!;
    ctx.scale(dpr, dpr);

    const values = data.map((d) => d.count);
    const max = Math.max(...values, 1);
    const min = 0;
    const range = max - min;

    const padX = 0;
    const padY = 4;
    const usableW = W - padX * 2;
    const usableH = H - padY * 2;

    const toX = (i: number) => padX + (i / (data.length - 1)) * usableW;
    const toY = (v: number) => padY + usableH - ((v - min) / range) * usableH;

    // Fill gradient
    const grad = ctx.createLinearGradient(0, padY, 0, H);
    grad.addColorStop(0, color + "40");
    grad.addColorStop(1, color + "00");

    ctx.beginPath();
    data.forEach((d, i) => {
      const x = toX(i);
      const y = toY(d.count);
      if (i === 0) ctx.moveTo(x, y);
      else {
        const px = toX(i - 1);
        const py = toY(data[i - 1].count);
        const cpx = (px + x) / 2;
        ctx.bezierCurveTo(cpx, py, cpx, y, x, y);
      }
    });
    ctx.lineTo(toX(data.length - 1), H);
    ctx.lineTo(toX(0), H);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Line
    ctx.beginPath();
    ctx.setLineDash([]);
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 6;
    data.forEach((d, i) => {
      const x = toX(i);
      const y = toY(d.count);
      if (i === 0) ctx.moveTo(x, y);
      else {
        const px = toX(i - 1);
        const py = toY(data[i - 1].count);
        const cpx = (px + x) / 2;
        ctx.bezierCurveTo(cpx, py, cpx, y, x, y);
      }
    });
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Current hour dot
    const now = new Date().getHours();
    const nowIndex = data.findIndex(d => parseInt(d.hour.split(':')[0]) === now);

    if (nowIndex !== -1 && values[nowIndex] !== undefined) {
      const cx = toX(nowIndex);
      const cy = toY(values[nowIndex]);
      ctx.beginPath();
      ctx.arc(cx, cy, 4, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.shadowColor = color;
      ctx.shadowBlur = 10;
      ctx.fill();
      ctx.shadowBlur = 0;
    }

    // Peak label
    const peakIdx = values.indexOf(Math.max(...values));
    const px = toX(peakIdx);
    const py = toY(values[peakIdx]) - 8;
    ctx.font = "bold 8px 'Share Tech Mono', monospace";
    ctx.fillStyle = color + "cc";
    ctx.textAlign = "center";
    ctx.fillText("PEAK", px, Math.max(8, py));
  }, [data, color, width, height]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full h-full"
      style={{ width: "100%", height: "100%" }}
    />
  );
}

// ─── Animated Counter ─────────────────────────────────────────

function AnimatedNumber({ target, suffix = "" }: { target: number; suffix?: string }) {
  const [display, setDisplay] = useState(0);
  const prevRef = useRef(0);

  useEffect(() => {
    const start = prevRef.current;
    const end = target;
    const duration = 800;
    const startTime = performance.now();

    const step = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(start + (end - start) * eased));
      if (progress < 1) requestAnimationFrame(step);
      else prevRef.current = end;
    };

    requestAnimationFrame(step);
  }, [target]);

  return (
    <span className="tabular-nums">
      {display.toLocaleString()}
      {suffix}
    </span>
  );
}

// ─── Main Component ───────────────────────────────────────────

const ACCENT_STYLES = {
  cyan: { text: "text-cyan-400", border: "border-cyan-900/40", glow: "shadow-[0_0_15px_rgba(0,245,255,0.1)]", bar: "#00f5ff" },
  green: { text: "text-green-400", border: "border-green-900/40", glow: "shadow-[0_0_15px_rgba(57,255,20,0.1)]", bar: "#39ff14" },
  yellow: { text: "text-yellow-400", border: "border-yellow-900/40", glow: "shadow-[0_0_15px_rgba(255,215,0,0.1)]", bar: "#ffd700" },
  pink: { text: "text-pink-400", border: "border-pink-900/40", glow: "shadow-[0_0_15px_rgba(255,0,170,0.1)]", bar: "#ff00aa" },
};

export default function StatsWidget() {
  const [hourlyData, setHourlyData] = useState<HourlyPoint[]>([]);
  const [stats, setStats] = useState({
    totalToday: 0,
    activeCameras: 0,
    totalCameras: 0,
    detPerHour: 0,
    uniquePersons: 0,
  });

  // New state variables for the display values
  const [peakHour, setPeakHour] = useState<string>("--:--");
  const [currentHourCount, setCurrentHourCount] = useState<number>(0);
  const [isClient, setIsClient] = useState(false);

  // 2. Mark when we are on the client
  useEffect(() => {
    setIsClient(true);
  }, []);

  // Fetch real stats
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch graph data
        const statsRes = await fetch("/api/stats/hourly");
        if (statsRes.ok) {
          const data = await statsRes.json();

          // Ensure we have 24 hours of data
          const fullDay: HourlyPoint[] = Array.from({ length: 24 }, (_, i) => ({
            hour: `${String(i).padStart(2, "0")}:00`,
            count: 0
          }));

          let totalDetectionsToday = 0;
          data.forEach((item: any) => {
            if (item.hour >= 0 && item.hour < 24) {
              fullDay[item.hour].count = item.count || 0;
              totalDetectionsToday += (item.count || 0);
            }
          });

          setHourlyData(fullDay);

          // Calculate stats
          const now = new Date().getHours();
          const currentHourDetections = fullDay[now].count;

          setStats(s => ({
            ...s,
            totalToday: totalDetectionsToday,
            detPerHour: currentHourDetections,
          }));

          // Fetch unique persons logic
          const uniqueRes = await fetch("/api/stats/unique-persons");
          if (uniqueRes.ok) {
            const uniqueData = await uniqueRes.json();
            setStats(s => ({ ...s, uniquePersons: uniqueData.count || 0 }));
          }
        }

        // Fetch camera status
        const camsRes = await fetch("/api/dashboard/cameras");
        if (camsRes.ok) {
          const camsData = await camsRes.json();
          const active = camsData.cameras?.filter((c: any) => c.is_processing).length || 0;
          const total = camsData.cameras?.length || 0;
          setStats(s => ({ ...s, activeCameras: active, totalCameras: total }));
        }

      } catch (err) {
        console.error("Failed to fetch stats dashboard data", err);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 60000); // 60s refresh
    return () => clearInterval(interval);
  }, []);

  // 3. Update the display values whenever `hourlyData` changes
  useEffect(() => {
    if (!isClient || hourlyData.length === 0) return;

    // Safe to use Date() here because we are in the browser
    const nowIndex = new Date().getHours();

    // Calculate Peak Hour
    const peak = hourlyData.reduce((a, b) => (a.count > b.count ? a : b));
    setPeakHour(peak.hour);

    // Calculate Current Hour Count (safely handle index bounds)
    const current = hourlyData.find(d => parseInt(d.hour.split(':')[0]) === nowIndex)?.count || 0;
    setCurrentHourCount(current);

  }, [hourlyData, isClient]);

  const cards: StatCard[] = [
    {
      label: "DETECTIONS TODAY",
      value: stats.totalToday,
      delta: +12,
      accent: "cyan",
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
          <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
        </svg>
      ),
    },
    {
      label: "ACTIVE CAMERAS",
      value: stats.activeCameras,
      suffix: `/${stats.totalCameras || 0}`,
      accent: "green",
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
          <path d="M15 10l4.553-2.277A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
        </svg>
      ),
    },
    {
      label: "DET / HOUR",
      value: stats.detPerHour,
      delta: +4,
      accent: "yellow",
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
        </svg>
      ),
    },
    {
      label: "UNIQUE PERSONS",
      value: stats.uniquePersons,
      suffix: " TODAY",
      accent: "pink",
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5">
          <path d="M12 12a5 5 0 100-10 5 5 0 000 10zm-7 9a7 7 0 1114 0" />
        </svg>
      ),
    },
  ];

  // const peakHour = hourlyData.reduce((a, b) => (a.count > b.count ? a : b)).hour;
  // const currentHourCount = hourlyData[new Date().getHours()].count;

  return (
    <div className="flex gap-3 flex-shrink-0">
      {/* ── Stat cards ── */}
      {cards.map((card) => {
        const style = ACCENT_STYLES[card.accent];
        return (
          <div
            key={card.label}
            className={`
              flex-1 hud-panel px-3 py-2.5 flex items-center gap-3
              ${style.border} ${style.glow}
              transition-all duration-300
            `}
          >
            {/* Icon */}
            <div className={`flex-shrink-0 ${style.text} opacity-60`}>
              {card.icon}
            </div>

            {/* Value + label */}
            <div className="flex-1 min-w-0">
              <div className={`font-orbitron text-lg font-bold leading-none ${style.text}`}>
                <AnimatedNumber target={card.value} suffix={card.suffix} />
              </div>
              <div className="font-mono text-[8px] text-slate-600 tracking-widest mt-0.5 truncate">
                {card.label}
              </div>
            </div>

            {/* Delta badge */}
            {card.delta !== undefined && (
              <div className={`
                flex-shrink-0 flex items-center gap-0.5 font-mono text-[9px]
                ${card.delta >= 0 ? "text-green-500" : "text-red-500"}
              `}>
                <svg viewBox="0 0 24 24" fill="currentColor" className="w-2.5 h-2.5">
                  <path d={card.delta >= 0 ? "M12 5l7 7H5z" : "M12 19l7-7H5z"} />
                </svg>
                {Math.abs(card.delta)}%
              </div>
            )}
          </div>
        );
      })}

      {/* ── Sparkline chart ── */}
      <div className="hud-panel px-3 py-2 flex flex-col min-w-0" style={{ width: 220 }}>
        <div className="flex items-center justify-between mb-1 flex-shrink-0">
          <span className="font-orbitron text-[9px] text-slate-500 tracking-widest">24H ACTIVITY</span>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[8px] text-slate-600">
              PEAK <span className="text-cyan-400">{peakHour}</span>
            </span>
          </div>
        </div>
        <div className="flex-1 min-h-0" style={{ height: 52 }}>
          <Sparkline data={hourlyData} color="#00f5ff" />
        </div>
        {/* Hour labels */}
        <div className="flex justify-between mt-0.5 flex-shrink-0">
          {["00", "06", "12", "18", "23"].map((h) => (
            <span key={h} className="font-mono text-[7px] text-slate-700">{h}</span>
          ))}
        </div>
        {/* Current */}
        <div className="flex items-center justify-between mt-1 flex-shrink-0">
          <span className="font-mono text-[8px] text-slate-600">NOW</span>
          <span className="font-mono text-[10px] text-cyan-400 font-bold tabular-nums">
            {currentHourCount} det
          </span>
        </div>
      </div>
    </div>
  );
}