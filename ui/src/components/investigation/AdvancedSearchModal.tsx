"use client";

import React, { useEffect, useCallback } from "react";
import { useInvestigation } from "./InvestigationContext";
import ClothingColorCard from "./ClothingColorCard";
import type { ClothingClass, DetailedColor, AdvancedFilter } from "@/types";

const CLOTHING_OPTIONS: ClothingClass[] = [
  "Long_sleeve",
  "Short_sleeve",
  "Trousers",
  "Shorts",
  "skirt",
  "Dress",
];

export default function AdvancedSearchModal() {
  const {
    state,
    closeAdvancedModal,
    addAdvancedFilter,
    removeAdvancedFilter,
    updateAdvancedFilter,
    setGlobalClothingLogic,
    clearAdvancedFilters,
    applyAdvancedSearch,
  } = useInvestigation();

  const { isAdvancedModalOpen, advancedFilters, globalClothingLogic } = state;

  // Handle ESC key to close modal
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") {
      closeAdvancedModal();
    }
  }, [closeAdvancedModal]);

  useEffect(() => {
    if (isAdvancedModalOpen) {
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "unset";
    };
  }, [isAdvancedModalOpen, handleKeyDown]);

  if (!isAdvancedModalOpen) return null;

  const getFilterForClothing = (clothing: ClothingClass): AdvancedFilter | undefined => {
    return advancedFilters.find((f) => f.clothing === clothing);
  };

  const handleColorsChange = (clothing: ClothingClass, colors: DetailedColor[]) => {
    const existing = getFilterForClothing(clothing);

    const filter: AdvancedFilter = {
      clothing,
      colors,
      colorLogic: existing?.colorLogic || "OR",
      includeWithoutColors: existing?.includeWithoutColors || false,
    };

    if (existing) {
      updateAdvancedFilter(filter);
    } else {
      addAdvancedFilter(filter);
    }
  };

  const handleLogicChange = (clothing: ClothingClass, logic: "OR" | "AND") => {
    const existing = getFilterForClothing(clothing);
    if (existing) {
      updateAdvancedFilter({ ...existing, colorLogic: logic });
    }
  };

  const handleIncludeWithoutColorsChange = (clothing: ClothingClass, include: boolean) => {
    const existing = getFilterForClothing(clothing);
    if (include) {
      // Add or update filter to include this clothing type
      const filter: AdvancedFilter = {
        clothing,
        colors: existing?.colors || [],
        colorLogic: existing?.colorLogic || "OR",
        includeWithoutColors: true,
      };
      if (existing) {
        updateAdvancedFilter(filter);
      } else {
        addAdvancedFilter(filter);
      }
    } else {
      // Remove filter or just uncheck includeWithoutColors if colors exist
      if (existing) {
        if (existing.colors.length === 0) {
          removeAdvancedFilter(clothing);
        } else {
          updateAdvancedFilter({ ...existing, includeWithoutColors: false });
        }
      }
    }
  };

  const activeFilterCount = advancedFilters.filter(f => f.includeWithoutColors || f.colors.length > 0).length;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm transition-opacity duration-300"
        onClick={closeAdvancedModal}
      />

      {/* Modal */}
      <div className="relative w-full max-w-4xl mx-4 bg-slate-900 border border-slate-700 rounded-lg shadow-2xl transform transition-all duration-300 scale-100 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/95">
          <div>
            <h2 className="font-mono text-sm text-cyan-400 tracking-wider uppercase">
              Advanced Search
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Configure specific colors for each clothing type
            </p>
          </div>
          <button
            onClick={closeAdvancedModal}
            className="w-8 h-8 flex items-center justify-center rounded-sm text-slate-500 hover:text-slate-300 hover:bg-slate-800/60 transition-all"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto">
          {/* Clothing Cards Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            {CLOTHING_OPTIONS.map((clothing) => {
              const filter = getFilterForClothing(clothing);
              return (
                <ClothingColorCard
                  key={clothing}
                  clothing={clothing}
                  selectedColors={filter?.colors || []}
                  colorLogic={filter?.colorLogic || "OR"}
                  includeWithoutColors={filter?.includeWithoutColors || false}
                  onColorsChange={(colors) => handleColorsChange(clothing, colors)}
                  onLogicChange={(logic) => handleLogicChange(clothing, logic)}
                  onIncludeWithoutColorsChange={(include) => handleIncludeWithoutColorsChange(clothing, include)}
                />
              );
            })}
          </div>

          {/* Global Logic Section */}
          <div className="flex items-center justify-between py-4 border-t border-slate-800/60">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-slate-400">Global Logic (between clothing items):</span>
              <div className="flex items-center gap-1 bg-slate-900/60 border border-slate-800 rounded-sm p-0.5">
                {(["OR", "AND"] as const).map((l) => (
                  <button
                    key={l}
                    onClick={() => setGlobalClothingLogic(l)}
                    className={`
                      px-3 py-1 rounded-sm font-mono text-[10px] tracking-wider transition-all
                      ${globalClothingLogic === l
                        ? "bg-cyan-900/60 text-cyan-400 border border-cyan-700/60"
                        : "text-slate-600 hover:text-slate-400"
                      }
                    `}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </div>
            <div className="text-xs text-slate-500">
              {activeFilterCount} item{activeFilterCount !== 1 ? "s" : ""} configured
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-800 bg-slate-900/95">
          <button
            onClick={() => {
              clearAdvancedFilters();
              closeAdvancedModal();
            }}
            className="px-4 py-2 rounded-sm font-mono text-xs text-slate-400 hover:text-slate-300 hover:bg-slate-800/60 transition-all"
          >
            Cancel
          </button>
          <button
            onClick={clearAdvancedFilters}
            disabled={activeFilterCount === 0}
            className="px-4 py-2 rounded-sm font-mono text-xs text-red-400 hover:text-red-300 hover:bg-red-950/30 border border-red-500/30 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            Clear All
          </button>
          <button
            onClick={() => {
              applyAdvancedSearch();
              // Search will be triggered by useEffect when advancedMode changes
            }}
            disabled={activeFilterCount === 0}
            className="px-4 py-2 rounded-sm font-mono text-xs bg-cyan-600/20 text-cyan-400 border border-cyan-500/40 hover:bg-cyan-600/30 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            Apply Search
          </button>
        </div>
      </div>
    </div>
  );
}
