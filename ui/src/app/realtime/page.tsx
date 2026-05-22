import RealtimeTab from "@/components/realtime/RealtimeTab";

export const metadata = {
  title: "NEXUS-EYE // Video Processing",
};

export default function RealtimePage() {
  return (
    <div className="h-full p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-orbitron text-xl font-bold text-red-400 tracking-[0.2em] uppercase">
            VIDEO PROCESSING
          </h1>
          <p className="font-mono text-[10px] text-slate-500 mt-0.5 tracking-widest">
            VIDEO · YOUTUBE · IPCAM · WEBCAM PROCESSING
          </p>
        </div>
        <div className="font-mono text-[10px] text-slate-600 border border-slate-800 px-3 py-1 rounded-sm">
          MODE: <span className="text-red-400">MULTI-SOURCE</span>
        </div>
      </div>

      {/* Realtime Content */}
      <div className="flex-1 min-h-0">
        <RealtimeTab />
      </div>
    </div>
  );
}
