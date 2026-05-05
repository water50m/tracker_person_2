import InputManagerTabs from "@/components/input-manager/InputManagerTabs";

export const metadata = {
  title: "NEXUS-EYE // Input Manager",
};

export default function InputManagerPage() {
  return (
    <div className="h-full p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1
            className="font-orbitron text-xl font-bold text-yellow-400 tracking-[0.2em] uppercase"
          >
            INPUT MANAGER
          </h1>
          <p className="font-mono text-[10px] text-slate-500 mt-0.5 tracking-widest">
            VIDEO INGESTION & CAMERA STREAM MANAGEMENT
          </p>
        </div>
        <div className="font-mono text-[10px] text-slate-600 border border-slate-800 px-3 py-1 rounded-sm">
          CAPACITY: <span className="text-yellow-400">12/32 FEEDS</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex-1 min-h-0">
        <InputManagerTabs />
      </div>
    </div>
  );
}
