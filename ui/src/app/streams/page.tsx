import RTSPTab from "@/components/input-manager/RTSPTab";

export const metadata = {
  title: "NEXUS-EYE // Streams",
};

export default function StreamsPage() {
  return (
    <div className="h-full p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-orbitron text-xl font-bold text-violet-400 tracking-[0.2em] uppercase">
            STREAM REGISTRY
          </h1>
          <p className="font-mono text-[10px] text-slate-500 mt-0.5 tracking-widest">
            SAVE RTSP URL FOR DASHBOARD VIEW WITHOUT STARTING AI PROCESSING
          </p>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <RTSPTab />
      </div>
    </div>
  );
}
