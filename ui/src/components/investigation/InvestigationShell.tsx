"use client";

import { InvestigationProvider, useInvestigation } from "./InvestigationContext";
import SearchFilterBar from "./SearchFilterBar";
import ResultsGrid from "./ResultsGrid";
import TraceModal from "./TraceModal";
import ImageModal from "./ImageModal";
import AdvancedSearchModal from "./AdvancedSearchModal";
import { DebugPanel } from "@/components/debug";

/**
 * InvestigationShell
 *
 * Wraps all investigation components in the shared context provider
 * and renders the TraceModal at the top level so it can use the portal overlay.
 *
 * Usage in app/investigation/page.tsx:
 *   import InvestigationShell from "@/components/investigation/InvestigationShell"
 *   <InvestigationShell />
 */
// DebugPanel wrapper to access context inside provider
function DebugPanelWrapper() {
  const { autoFillImage, autoFillResult, autoFillStatus } = useInvestigation();

  // Only show when there's analysis result
  if (autoFillStatus === "idle" || autoFillStatus === "analyzing") return null;

  return (
    <DebugPanel
      lastImage={autoFillImage}
      response={
        autoFillResult
          ? {
              status: autoFillStatus === "done" ? "success" : "error",
              detected_attributes: {
                class_name: autoFillResult.detected_attributes?.class_name,
                color_name: autoFillResult.detected_attributes?.color_name,
                category: autoFillResult.detected_attributes?.category,
                confidence: autoFillResult.detected_attributes?.confidence,
              },
              all_items: autoFillResult.all_items,
            }
          : null
      }
    />
  );
}

export default function InvestigationShell() {
  return (
    <InvestigationProvider>
      {/* Filter bar */}
      <SearchFilterBar />

      {/* Results */}
      <ResultsGrid />

      {/* Trace modal — rendered outside the grid flow via fixed positioning */}
      <TraceModal />

      {/* Image modal — for showing enlarged image with trace/video buttons */}
      <ImageModal />

      {/* Advanced Search modal — rendered at top level to avoid z-index issues */}
      <AdvancedSearchModal />

      {/* Debug Panel — shows image analysis results in bottom-right */}
      <DebugPanelWrapper />
    </InvestigationProvider>
  );
}