"use client";

import React, { useState, useEffect } from "react";
import type { ClothingClass, DetailedColor } from "@/types";

// Tone to detailed colors mapping (same as in SearchFilterBar)
const TONE_TO_DETAILED_COLORS: Record<string, { value: string; label: string; hex: string }[]> = {
  red_tones: [
    { value: "red", label: "Red", hex: "#ef4444" },
    { value: "dark_red", label: "Dark Red", hex: "#991b1b" },
    { value: "crimson", label: "Crimson", hex: "#dc143c" },
    { value: "scarlet", label: "Scarlet", hex: "#ff2400" },
    { value: "maroon", label: "Maroon", hex: "#800000" },
  ],
  orange_tones: [
    { value: "orange", label: "Orange", hex: "#f97316" },
    { value: "dark_orange", label: "Dark Orange", hex: "#c2410c" },
    { value: "amber", label: "Amber", hex: "#f59e0b" },
    { value: "peach", label: "Peach", hex: "#fcd34d" },
    { value: "coral", label: "Coral", hex: "#fb923c" },
  ],
  yellow_tones: [
    { value: "yellow", label: "Yellow", hex: "#eab308" },
    { value: "gold", label: "Gold", hex: "#fbbf24" },
    { value: "light_yellow", label: "Light Yellow", hex: "#fef08a" },
    { value: "mustard", label: "Mustard", hex: "#a16207" },
    { value: "khaki", label: "Khaki", hex: "#ca8a04" },
  ],
  green_tones: [
    { value: "green", label: "Green", hex: "#22c55e" },
    { value: "dark_green", label: "Dark Green", hex: "#166534" },
    { value: "light_green", label: "Light Green", hex: "#86efac" },
    { value: "olive", label: "Olive", hex: "#65a30d" },
    { value: "lime", label: "Lime", hex: "#84cc16" },
    { value: "forest_green", label: "Forest Green", hex: "#14532d" },
    { value: "mint", label: "Mint", hex: "#6ee7b7" },
    { value: "teal", label: "Teal", hex: "#14b8a6" },
  ],
  blue_tones: [
    { value: "blue", label: "Blue", hex: "#3b82f6" },
    { value: "dark_blue", label: "Dark Blue", hex: "#1e3a8a" },
    { value: "light_blue", label: "Light Blue", hex: "#93c5fd" },
    { value: "navy", label: "Navy", hex: "#1e3a5f" },
    { value: "sky_blue", label: "Sky Blue", hex: "#0ea5e9" },
    { value: "royal_blue", label: "Royal Blue", hex: "#4169e1" },
    { value: "cobalt", label: "Cobalt", hex: "#0047ab" },
    { value: "turquoise", label: "Turquoise", hex: "#40e0d0" },
  ],
  purple_tones: [
    { value: "purple", label: "Purple", hex: "#a855f7" },
    { value: "dark_purple", label: "Dark Purple", hex: "#6b21a8" },
    { value: "light_purple", label: "Light Purple", hex: "#d8b4fe" },
    { value: "violet", label: "Violet", hex: "#8b5cf6" },
    { value: "lavender", label: "Lavender", hex: "#a78bfa" },
    { value: "magenta", label: "Magenta", hex: "#d946ef" },
    { value: "fuchsia", label: "Fuchsia", hex: "#e879f9" },
    { value: "plum", label: "Plum", hex: "#9333ea" },
  ],
  brown_tones: [
    { value: "brown", label: "Brown", hex: "#92400e" },
    { value: "dark_brown", label: "Dark Brown", hex: "#78350f" },
    { value: "light_brown", label: "Light Brown", hex: "#d97706" },
    { value: "tan", label: "Tan", hex: "#b45309" },
    { value: "camel", label: "Camel", hex: "#c19a6b" },
  ],
  pink_tones: [
    { value: "pink", label: "Pink", hex: "#ec4899" },
    { value: "light_pink", label: "Light Pink", hex: "#f9a8d4" },
    { value: "hot_pink", label: "Hot Pink", hex: "#f472b6" },
    { value: "rose", label: "Rose", hex: "#fb7185" },
    { value: "salmon", label: "Salmon", hex: "#fa8072" },
  ],
  white_tones: [
    { value: "white", label: "White", hex: "#ffffff" },
    { value: "light_gray", label: "Light Gray", hex: "#d1d5db" },
    { value: "silver", label: "Silver", hex: "#c0c0c0" },
    { value: "beige", label: "Beige", hex: "#f5f5dc" },
  ],
  black_tones: [
    { value: "black", label: "Black", hex: "#000000" },
    { value: "dark_gray", label: "Dark Gray", hex: "#374151" },
  ],
};

const TONE_GROUP_OPTIONS = [
  { value: "red_tones", label: "\u0e41\u0e14\u0e07", color: "#ef4444" },
  { value: "orange_tones", label: "\u0e2a\u0e49\u0e21", color: "#f97316" },
  { value: "yellow_tones", label: "\u0e40\u0e2b\u0e25\u0e37\u0e2d\u0e07", color: "#eab308" },
  { value: "green_tones", label: "\u0e40\u0e02\u0e35\u0e22\u0e27", color: "#22c55e" },
  { value: "blue_tones", label: "\u0e19\u0e49\u0e33\u0e40\u0e07\u0e34\u0e19", color: "#3b82f6" },
  { value: "purple_tones", label: "\u0e21\u0e48\u0e27\u0e07", color: "#a855f7" },
  { value: "brown_tones", label: "\u0e19\u0e49\u0e33\u0e15\u0e32\u0e25", color: "#92400e" },
  { value: "pink_tones", label: "\u0e0a\u0e21\u0e1e\u0e39", color: "#ec4899" },
  { value: "white_tones", label: "\u0e02\u0e32\u0e27", color: "#f8fafc" },
  { value: "black_tones", label: "\u0e14\u0e33", color: "#0f172a" },
] as const;

interface ClothingColorCardProps {
  clothing: ClothingClass;
  selectedColors: DetailedColor[];
  colorLogic: "OR" | "AND";
  includeWithoutColors: boolean;
  onColorsChange: (colors: DetailedColor[]) => void;
  onLogicChange: (logic: "OR" | "AND") => void;
  onIncludeWithoutColorsChange: (include: boolean) => void;
}

export default function ClothingColorCard({
  clothing,
  selectedColors,
  colorLogic,
  includeWithoutColors,
  onColorsChange,
  onLogicChange,
  onIncludeWithoutColorsChange,
}: ClothingColorCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandedToneGroup, setExpandedToneGroup] = useState<string | null>(null);

  // Auto-collapse colors when unchecked and no colors selected
  useEffect(() => {
    if (!includeWithoutColors && selectedColors.length === 0) {
      setIsExpanded(false);
    }
  }, [includeWithoutColors, selectedColors.length]);

  const handleCardClick = (e: React.MouseEvent) => {
    // Prevent triggering when clicking on interactive elements
    const target = e.target as HTMLElement;
    if (
      target.tagName === "INPUT" ||
      target.tagName === "BUTTON" ||
      target.closest("button") ||
      target.closest(".color-selector-area")
    ) {
      return;
    }
    // Toggle the checkbox
    onIncludeWithoutColorsChange(!includeWithoutColors);
  };

  const toggleColor = (color: DetailedColor) => {
    if (selectedColors.includes(color)) {
      onColorsChange(selectedColors.filter((c) => c !== color));
    } else {
      onColorsChange([...selectedColors, color]);
    }
  };

  const isActive = selectedColors.length > 0 || includeWithoutColors;

  return (
    <div
      onClick={handleCardClick}
      className={`
        relative rounded-sm border p-3 transition-all duration-200 cursor-pointer
        ${isActive
          ? "border-cyan-500/50 bg-cyan-950/20 shadow-[0_0_15px_rgba(6,182,212,0.15)]"
          : "border-slate-800 bg-slate-900/40 hover:border-slate-700"
        }
      `}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeWithoutColors}
            onChange={(e) => onIncludeWithoutColorsChange(e.target.checked)}
            className="w-3.5 h-3.5 rounded-sm border border-slate-600 bg-slate-900/60 text-cyan-500 focus:ring-cyan-500/50 cursor-pointer"
          />
          <h3 className="font-mono text-xs text-slate-300 uppercase tracking-wider">
            {clothing.replace(/_/g, " ")}
          </h3>
        </div>
        {isActive && (
          <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/50 px-1.5 py-0.5 rounded-sm">
            {selectedColors.length > 0 ? `${selectedColors.length} color${selectedColors.length !== 1 ? "s" : ""}` : "All Colors"}
          </span>
        )}
      </div>

      {/* Expand/Collapse Button */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          setIsExpanded(!isExpanded);
        }}
        disabled={!includeWithoutColors && selectedColors.length === 0}
        className={`
          w-full flex items-center justify-between
          px-2 py-1.5 rounded-sm border border-slate-700/60
          transition-all duration-150
          font-mono text-[10px]
          ${!includeWithoutColors && selectedColors.length === 0
            ? "bg-slate-900/30 text-slate-600 cursor-not-allowed"
            : "bg-slate-900/60 hover:bg-slate-800/60 text-slate-400 hover:text-slate-300 cursor-pointer"
          }
        `}
      >
        <span>{isExpanded ? "Hide Colors" : selectedColors.length > 0 ? "Edit Colors" : "Select Colors (Optional)"}</span>
        <span className={`transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`}>
          ▼
        </span>
      </button>

      {/* Color Selector (Expandable) */}
      {isExpanded && (
        <div className="mt-3 space-y-2 color-selector-area" onClick={(e) => e.stopPropagation()}>
          {/* OR/AND Toggle */}
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-slate-500">Color Logic:</span>
            <div className="flex items-center gap-1 bg-slate-900/60 border border-slate-800 rounded-sm p-0.5">
              {(["OR", "AND"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => onLogicChange(l)}
                  className={`
                    px-2 py-0.5 rounded-sm font-mono text-[9px] tracking-wider transition-all
                    ${colorLogic === l
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

          {/* Tone Groups */}
          <div className="flex flex-wrap gap-1.5">
            {TONE_GROUP_OPTIONS.map(({ value, label, color }) => {
              const detailedColors = TONE_TO_DETAILED_COLORS[value] || [];
              const allSubColorsSelected = detailedColors.length > 0 &&
                detailedColors.every(dc => selectedColors.includes(dc.value as DetailedColor));
              const someSubColorsSelected = detailedColors.some(dc => selectedColors.includes(dc.value as DetailedColor));

              return (
                <div key={value} className="relative">
                  <button
                    onClick={() => {
                      const subColorValues = detailedColors.map(dc => dc.value as DetailedColor);
                      if (allSubColorsSelected) {
                        onColorsChange(selectedColors.filter(c => !subColorValues.includes(c)));
                      } else {
                        const newColors = [...selectedColors];
                        subColorValues.forEach(sc => {
                          if (!newColors.includes(sc)) newColors.push(sc);
                        });
                        onColorsChange(newColors);
                      }
                    }}
                    title={value}
                    className={`
                      relative flex items-center gap-1 px-1.5 py-0.5 rounded-sm border font-mono text-[9px]
                      transition-all duration-150
                      ${allSubColorsSelected
                        ? "border-white/30 bg-white/5 text-white shadow-sm"
                        : someSubColorsSelected
                          ? "border-white/20 bg-white/3 text-white/80"
                          : "border-slate-800 text-slate-600 hover:border-slate-600 hover:text-slate-400"
                      }
                    `}
                    style={allSubColorsSelected ? { borderColor: color + "60", boxShadow: `0 0 6px ${color}30` } : {}}
                  >
                    <span
                      className={`w-2 h-2 rounded-full border flex-shrink-0 transition-all ${allSubColorsSelected ? "scale-110" : "scale-90"}`}
                      style={{
                        background: color,
                        borderColor: allSubColorsSelected ? color : "rgba(255,255,255,0.1)",
                        boxShadow: allSubColorsSelected ? `0 0 4px ${color}80` : "none",
                      }}
                    />
                    <span style={allSubColorsSelected ? { color } : {}}>{label}</span>
                    <span
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedToneGroup(expandedToneGroup === value ? null : value);
                      }}
                      className="ml-1 text-[8px] text-slate-500 hover:text-slate-300 cursor-pointer px-0.5 select-none"
                    >
                      {expandedToneGroup === value ? "▼" : "▶"}
                    </span>
                  </button>

                  {/* Detailed colors dropdown */}
                  {expandedToneGroup === value && TONE_TO_DETAILED_COLORS[value] && (
                    <div className="absolute bottom-full left-0 mb-1 z-[100] bg-slate-900 border border-slate-700 rounded-sm p-1.5 shadow-xl min-w-[160px]">
                      <div className="flex flex-wrap gap-1">
                        {TONE_TO_DETAILED_COLORS[value].map(({ value: dcValue, label: dcLabel, hex }) => (
                          <button
                            key={dcValue}
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleColor(dcValue as DetailedColor);
                            }}
                            title={dcLabel}
                            className={`
                              relative flex items-center gap-1 px-1 py-0.5 rounded-sm border font-mono text-[8px]
                              transition-all duration-150
                              ${selectedColors.includes(dcValue as DetailedColor)
                                ? "border-white/30 bg-white/5 text-white"
                                : "border-slate-800 text-slate-600 hover:border-slate-600"
                              }
                            `}
                            style={selectedColors.includes(dcValue as DetailedColor) ? { borderColor: hex + "40" } : {}}
                          >
                            <span
                              className="w-1.5 h-1.5 rounded-full border flex-shrink-0"
                              style={{
                                background: hex,
                                borderColor: selectedColors.includes(dcValue as DetailedColor) ? hex : "rgba(255,255,255,0.1)",
                              }}
                            />
                            <span style={selectedColors.includes(dcValue as DetailedColor) ? { color: hex } : {}}>{dcLabel}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Selected Colors Display */}
          {selectedColors.length > 0 && (
            <div className="pt-2 border-t border-slate-800/60">
              <span className="font-mono text-[9px] text-slate-500 block mb-1">Selected:</span>
              <div className="flex flex-wrap gap-1">
                {selectedColors.map((color) => {
                  const colorInfo = Object.values(TONE_TO_DETAILED_COLORS)
                    .flat()
                    .find(c => c.value === color);
                  return (
                    <button
                      key={color}
                      onClick={() => toggleColor(color)}
                      className="flex items-center gap-1 px-1.5 py-0.5 rounded-sm bg-slate-800/60 border border-slate-700/60 text-[9px] text-slate-300 hover:border-red-500/40 hover:text-red-400 transition-all"
                    >
                      <span
                        className="w-1.5 h-1.5 rounded-full"
                        style={{ background: colorInfo?.hex || "#666" }}
                      />
                      {colorInfo?.label || color}
                      <span className="text-slate-500">×</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
