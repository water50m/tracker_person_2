import InvestigationShell from "@/components/investigation/InvestigationShell";

export const metadata = {
  title: "NEXUS-EYE // Investigation",
};

export default function InvestigationPage() {
  return (
    <div className="h-full p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1
            className="font-orbitron text-xl font-bold text-pink-400 tracking-[0.2em] uppercase glitch-text"
            data-text="INVESTIGATION"
          >
            INVESTIGATION
          </h1>
          <p className="font-mono text-[10px] text-slate-500 mt-0.5 tracking-widest">
            SEARCH & TRACE SUSPECTS · ATTRIBUTE-BASED FILTERING
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="font-mono text-[10px] text-slate-600 border border-slate-800 px-3 py-1 rounded-sm">
            AUTO-FILL MODE: <span className="text-cyan-400">ACTIVE</span>
          </div>
          <div className="font-mono text-[10px] text-slate-600 border border-slate-800 px-3 py-1 rounded-sm">
            ENGINE: <span className="text-yellow-400">ATTRIBUTE-SEARCH</span>
          </div>
        </div>
      </div>

      {/* Shell: provides context + renders FilterBar + ResultsGrid + TraceModal */}
      <div className="flex-1 grid grid-rows-[auto_1fr] gap-4 min-h-0">
        <InvestigationShell />
      </div>
    </div>
  );
}