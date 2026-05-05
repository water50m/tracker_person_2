"use client";

import { useState } from "react";
import { ColorSwatch } from "./ColorSwatch";
import { extractColors } from "@/lib/color-utils";

const CATEGORY_HEX_MAP: Record<string, string> = {
  // Temperature
  warm_colors: "#f97316", cool_colors: "#3b82f6", neutral_colors: "#6b7280",
  // Brightness
  light_colors: "#f8fafc", medium_colors: "#9ca3af", dark_colors: "#1f2937",
  // Vibrancy
  vibrant_colors: "#ef4444", muted_colors: "#6b7280", pastel_colors: "#fbcfe8",
  // Clothing
  common_shirt_colors: "#3b82f6", common_pants_colors: "#92400e",
  formal_colors: "#1e3a8a", casual_colors: "#22c55e",
};

interface DebugPanelProps {
  lastImage?: string | null;
  response?: {
    status?: string;
    detected_attributes?: {
      class_name?: string;
      color_name?: string;
      category?: string;
      confidence?: number;
    };
    all_items?: Array<{
      class_name?: string;
      color?: string;
      category?: string;
      confidence: number;
      detailed_colors?: Record<string, number>;
      color_categories?: {
        brightness_groups?: Record<string, number>;
        vibrancy_groups?: Record<string, number>;
        temperature_groups?: Record<string, number>;
        clothing_groups?: Record<string, number>;
      };
    }>;
    processing_time_ms?: number;
    num_persons_detected?: number;
  } | null;
}

export function DebugPanel({ lastImage, response }: DebugPanelProps) {
  const [isMinimized, setIsMinimized] = useState(false);
  const [showRawJson, setShowRawJson] = useState(false);

  // Log props received
  if (response) {
    console.log("[DEBUG_PANEL] Props received:", { response });
    const colors = extractColors(response);
    console.log("[DEBUG_PANEL] Colors extracted:", colors);
  }

  if (!response) return null;

  const colors = extractColors(response);
  const isSuccess = response.status === "success";

  return (
    <div className="fixed bottom-4 right-4 z-50 bg-slate-900/95 backdrop-blur rounded-lg shadow-2xl border border-cyan-500/30 w-80 text-slate-200">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700 bg-slate-800/50 rounded-t-lg">
        <span className="text-sm font-semibold text-cyan-400 font-orbitron tracking-wider">IMAGE ANALYSIS DEBUG</span>
        <div className="flex gap-1">
          <button
            onClick={() => setIsMinimized(!isMinimized)}
            className="p-1 hover:bg-slate-700 rounded text-slate-400 hover:text-cyan-400 transition-colors"
          >
            {isMinimized ? "□" : "_"}
          </button>
        </div>
      </div>

      {!isMinimized && (
        <div className="p-3 space-y-3">
          {/* Image Preview */}
          {lastImage && (
            <div className="flex justify-center">
              <img
                src={lastImage}
                alt="Analyzed"
                className="max-w-[120px] max-h-[720px] rounded-lg object-contain border border-slate-600"
              />
            </div>
          )}

          {/* Basic Info */}
          <div className="text-sm space-y-1 font-mono">
            <div className="flex items-center gap-2">
              <span className="text-slate-400">STATUS:</span>
              <span className={isSuccess ? "text-green-400" : "text-red-400"}>
                {isSuccess ? "✓" : "✗"} {response.status?.toUpperCase()}
              </span>
            </div>
            {/* {response.detected_attributes?.class_name && (
              <div>
                <span className="text-slate-400">CLASS:</span>{" "}
                <span className="font-medium text-cyan-300">
                  {response.detected_attributes.class_name}
                </span>
              </div>
            )} */}
            {/* {response.detected_attributes?.category && (
              <div>
                <span className="text-slate-400">CATEGORY:</span>{" "}
                <span className="text-slate-200">{response.detected_attributes.category}</span>
              </div>
            )} */}
            {/* {response.detected_attributes?.confidence !== undefined && (
              <div>
                <span className="text-slate-400">CONFIDENCE:</span>{" "}
                <span className="text-yellow-400">
                  {(response.detected_attributes.confidence * 100).toFixed(1)}%
                </span>
              </div>
            )} */}
          </div>

          {/* All Items with Colors */}
          {response.all_items && response.all_items.length > 0 && (
            <div className="border-t border-slate-700 pt-2">
              <div className="text-sm font-medium text-slate-400 mb-2 font-mono">
                ALL ITEMS ({response.all_items.length}):
              </div>
              <div className="space-y-2 text-xs">
                {response.all_items.map((item, idx) => {
                  // Get top 3 colors from detailed_colors with percentages
                  const itemColors: Array<{ name: string; percentage: number }> = [];
                  if (item.detailed_colors && typeof item.detailed_colors === 'object') {
                    const detailed = item.detailed_colors;
                    const sortedColors = Object.entries(detailed)
                      .sort(([, a], [, b]) => (b as number) - (a as number))
                      .slice(0, 3);
                    itemColors.push(...sortedColors.map(([name, pct]) => ({ name: name.toLowerCase(), percentage: pct as number })));
                  } else if (item.color) {
                    itemColors.push({ name: item.color.toLowerCase(), percentage: 0 });
                  }

                  return (
                    <div key={idx} className="bg-slate-800/50 rounded p-2">
                      <div className="flex items-center gap-2 text-slate-300 mb-1">
                        <span className="text-cyan-400">{idx + 1}.</span>
                        <span className="font-medium">{item.class_name}</span>
                        <span className="text-slate-500"> {(item.confidence * 100).toFixed(1)}% </span>
                      </div>
                      {itemColors.length > 0 && (
                        <div className="flex flex-wrap gap-1 ml-5">
                          {itemColors.map((color, colorIdx) => (
                            <ColorSwatch key={colorIdx} colorName={color.name} percentage={color.percentage} size="sm" />
                          ))}
                        </div>
                      )}
                      {item.color_categories && (
                        <div className="ml-5 mt-1 space-y-1 text-slate-400">
                          {item.color_categories.brightness_groups && Object.keys(item.color_categories.brightness_groups).length > 0 && (
                            <div className="text-[10px] flex items-center gap-1">
                              <span className="text-slate-500">Brightness:</span>
                              {Object.entries(item.color_categories.brightness_groups).map(([name, pct]) => (
                                <div key={name} className="flex items-center gap-1">
                                  <div
                                    className="w-3 h-3 rounded border border-gray-300"
                                    style={{ backgroundColor: CATEGORY_HEX_MAP[name] || "#cccccc" }}
                                  />
                                  <span>{(pct as number).toFixed(0)}%</span>
                                </div>
                              ))}
                            </div>
                          )}
                          {item.color_categories.vibrancy_groups && Object.keys(item.color_categories.vibrancy_groups).length > 0 && (
                            <div className="text-[10px] flex items-center gap-1">
                              <span className="text-slate-500">Vibrancy:</span>
                              {Object.entries(item.color_categories.vibrancy_groups).map(([name, pct]) => (
                                <div key={name} className="flex items-center gap-1">
                                  <div
                                    className="w-3 h-3 rounded border border-gray-300"
                                    style={{ backgroundColor: CATEGORY_HEX_MAP[name] || "#cccccc" }}
                                  />
                                  <span>{(pct as number).toFixed(0)}%</span>
                                </div>
                              ))}
                            </div>
                          )}
                          {item.color_categories.temperature_groups && Object.keys(item.color_categories.temperature_groups).length > 0 && (
                            <div className="text-[10px] flex items-center gap-1">
                              <span className="text-slate-500">Temperature:</span>
                              {Object.entries(item.color_categories.temperature_groups).map(([name, pct]) => (
                                <div key={name} className="flex items-center gap-1">
                                  <div
                                    className="w-3 h-3 rounded border border-gray-300"
                                    style={{ backgroundColor: CATEGORY_HEX_MAP[name] || "#cccccc" }}
                                  />
                                  <span>{(pct as number).toFixed(0)}%</span>
                                </div>
                              ))}
                            </div>
                          )}
                          {item.color_categories.clothing_groups && Object.keys(item.color_categories.clothing_groups).length > 0 && (
                            <div className="text-[10px] flex items-center gap-1">
                              <span className="text-slate-500">Clothing:</span>
                              {Object.entries(item.color_categories.clothing_groups).map(([name, pct]) => (
                                <div key={name} className="flex items-center gap-1">
                                  <div
                                    className="w-3 h-3 rounded border border-gray-300"
                                    style={{ backgroundColor: CATEGORY_HEX_MAP[name] || "#cccccc" }}
                                  />
                                  <span>{(pct as number).toFixed(0)}%</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Raw JSON Toggle */}
          <details className="text-xs border-t border-slate-700 pt-2">
            <summary
              className="cursor-pointer text-slate-500 hover:text-cyan-400 select-none font-mono"
              onClick={() => setShowRawJson(!showRawJson)}
            >
              ▼ VIEW RAW JSON
            </summary>
            <pre className="mt-2 p-2 bg-slate-800 rounded overflow-x-auto text-[10px] text-slate-300">
              {JSON.stringify(response, null, 2)}
            </pre>
          </details>
        </div>
      )}

      {isMinimized && colors.length > 0 && (
        <div className="px-3 py-2 flex items-center gap-2">
          <span className="text-xs text-gray-500">Colors:</span>
          <div className="flex gap-1">
            {colors.slice(0, 3).map((color, idx) => (
              <div
                key={idx}
                className="w-4 h-4 rounded border border-gray-300"
                style={{ backgroundColor: getColorHex(color) }}
                title={color}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Helper for minimized view
function getColorHex(colorName: string): string {
  const COLOR_HEX_MAP: Record<string, string> = {
    red: "#ef4444",
    dark_red: "#991b1b",
    green: "#22c55e",
    blue: "#3b82f6",
    navy: "#1e3a8a",
    purple: "#a855f7",
    pink: "#ec4899",
    black: "#000000",
    white: "#ffffff",
    gray: "#6b7280",
    yellow: "#eab308",
    orange: "#f97316",
  };
  if (!colorName) return "#cccccc";
  const normalized = colorName.toLowerCase().replace(/\s+/g, "_");
  return COLOR_HEX_MAP[normalized] || "#cccccc";
}
