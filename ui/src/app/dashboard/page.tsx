import LiveVideoCanvas from "@/components/dashboard/LiveVideoCanvas";
import EventFeed from "@/components/dashboard/EventFeed";
import StatsWidget from "@/components/dashboard/StatsWidget";

export const metadata = {
  title: "NEXUS-EYE // Dashboard",
};

export default function DashboardPage() {
  return (
    <div className="h-full p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1
            className="font-orbitron text-xl font-bold text-cyan-400 tracking-[0.2em] uppercase glitch-text"
            data-text="LIVE MONITOR"
          >
            LIVE MONITOR
          </h1>
          <p className="font-mono text-[10px] text-slate-500 mt-0.5 tracking-widest">
            REAL-TIME SURVEILLANCE OVERVIEW
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="status-live">SYSTEM ONLINE</div>
          <div className="font-mono text-xs text-slate-500">
            <LiveClock />
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <StatsWidget />

      {/* Main Grid: Video + Event Feed */}
      <div className="flex-1 grid grid-cols-[1fr_320px] gap-4 min-h-0">
        <LiveVideoCanvas />
        <EventFeed />
      </div>
    </div>
  );
}

// Small server-compatible clock placeholder
function LiveClock() {
  return <span suppressHydrationWarning>{new Date().toUTCString()}</span>;
}