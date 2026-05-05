"use client";

import React, { useCallback, useRef, useState, useEffect } from "react";
import Image from "next/image";
import { useInvestigation } from "./InvestigationContext";
import type { ClothingClass, ClothingColor, AttributeDetectionResult } from "@/types";
import { API } from "@/lib/api"; // FastAPI base URL จาก .env.local

interface CameraOption { id: string; name: string; }
interface VideoOption { id: string; filename: string; camera_id: string; status: string; }

// ─── Constants ───────────────────────────────────────────────

const CLOTHING_OPTIONS: ClothingClass[] = [
  "Long_sleeve",
  "Short_sleeve",
  "Trousers",
  "Shorts",
  "skirt",
  "Dress",
];

const COLOR_OPTIONS: { value: ClothingColor; hex: string; label: string }[] = [
  { value: "Red", hex: "#ef4444", label: "RED" },
  { value: "Orange", hex: "#f97316", label: "ORG" },
  { value: "Yellow", hex: "#eab308", label: "YEL" },
  { value: "Green", hex: "#22c55e", label: "GRN" },
  { value: "Blue", hex: "#3b82f6", label: "BLU" },
  { value: "Navy", hex: "#1e3a5f", label: "NAV" },
  { value: "Purple", hex: "#a855f7", label: "PUR" },
  { value: "Pink", hex: "#ec4899", label: "PNK" },
  { value: "White", hex: "#f8fafc", label: "WHT" },
  { value: "Gray", hex: "#6b7280", label: "GRY" },
  { value: "Brown", hex: "#92400e", label: "BRN" },
  { value: "Black", hex: "#0f172a", label: "BLK" },
];

// New color system options (10 tone groups)
const TONE_GROUP_OPTIONS = [
  { value: "red_tones", label: "แดง", color: "#ef4444" },
  { value: "orange_tones", label: "ส้ม", color: "#f97316" },
  { value: "yellow_tones", label: "เหลือง", color: "#eab308" },
  { value: "green_tones", label: "เขียว", color: "#22c55e" },
  { value: "blue_tones", label: "น้ำเงิน", color: "#3b82f6" },
  { value: "purple_tones", label: "ม่วง", color: "#a855f7" },
  { value: "brown_tones", label: "น้ำตาล", color: "#92400e" },
  { value: "pink_tones", label: "ชมพู", color: "#ec4899" },
  { value: "white_tones", label: "ขาว", color: "#f8fafc" },
  { value: "black_tones", label: "ดำ", color: "#0f172a" },
] as const;

const TEMPERATURE_OPTIONS = [
  { value: "warm", label: "อุ่น", color: "#f97316" },
  { value: "cool", label: "เย็น", color: "#3b82f6" },
  { value: "neutral", label: "กลาง", color: "#6b7280" },
] as const;

const BRIGHTNESS_OPTIONS = [
  { value: "light", label: "สว่าง", color: "#f8fafc" },
  { value: "medium", label: "ปานกลาง", color: "#9ca3af" },
  { value: "dark", label: "เข้ม", color: "#1f2937" },
] as const;

const VIBRANCY_OPTIONS = [
  { value: "vibrant", label: "สดใส", color: "#ef4444" },
  { value: "muted", label: "กลางๆ", color: "#6b7280" },
  { value: "pastel", label: "พาสเทล", color: "#fbcfe8" },
] as const;

// Tone to detailed colors mapping
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

// ─── Component ───────────────────────────────────────────────

type ColorTab = "color" | "temp" | "brightness" | "vibrancy";

export default function SearchFilterBar() {
  const {
    state, toggleClothing, toggleColor, setLogic, setThreshold,
    setCamera, setVideo, setTimeRange, resetFilters, runSearch,
    submitAutoFill, clearAutoFill,
    // Secondary color filters
    setTemperature, setBrightness, setVibrancy,
    // Advanced search
    openAdvancedModal, clearAdvancedFilters
  } = useInvestigation();
  const { filters, autoFillImage, autoFillStatus, autoFillResult, isSearching, advancedFilters, advancedMode } = state;

  const [isDragOver, setIsDragOver] = useState(false);
  const [activeColorTab, setActiveColorTab] = useState<ColorTab>("color");
  const [expandedToneGroup, setExpandedToneGroup] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Camera & Video lists from API ──────────────────────────
  const [cameras, setCameras] = useState<CameraOption[]>([]);
  const [allVideos, setAllVideos] = useState<VideoOption[]>([]);

  useEffect(() => {
    // ดึง camera_ids ที่มีใน detections — เรียก FastAPI โดยตรง
    fetch(`${API}/api/video/detections?limit=500`)
      .then((r) => r.json())
      .then((d: any[]) => {
        const ids = Array.from(new Set(d.map((x) => x.camera_id).filter(Boolean))) as string[];
        setCameras(ids.map((id) => ({ id, name: id })));
      })
      .catch(() => setCameras([]));
    // ดึงรายการวิดีโอ — เรียก FastAPI โดยตรง
    fetch(`${API}/api/video/videos`)
      .then((r) => r.json())
      .then((d) => setAllVideos(Array.isArray(d) ? d : []))
      .catch(() => setAllVideos([]));
  }, []);

  const cameraVideos = filters.camera_id
    ? allVideos.filter((v) => v.camera_id === filters.camera_id && v.status === "completed")
    : allVideos.filter((v) => v.status === "completed");

  // ── Drag & Drop ──────────────────────────────────────────────
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file && file.type.startsWith("image/")) submitAutoFill(file);
    },
    [submitAutoFill]
  );

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) submitAutoFill(file);
    e.target.value = "";
  };

  // ── Auto search on filter change ───────────────────────
  useEffect(() => {
    const timer = setTimeout(() => { runSearch(); }, 300);
    return () => clearTimeout(timer);
  }, [
    filters.clothing, filters.colors, filters.logic, filters.threshold,
    filters.temperature, filters.brightness, filters.vibrancy, filters.clothing_groups,
    filters.camera_id, filters.video_id, filters.start_time, filters.end_time
  ]);

  const activeFilterCount =
    filters.clothing.length +
    filters.colors.length +
    (filters.temperature ? 1 : 0) +
    (filters.brightness ? 1 : 0) +
    (filters.vibrancy ? 1 : 0) +
    (filters.clothing_groups?.length || 0) +
    (filters.camera_id ? 1 : 0) +
    (filters.video_id ? 1 : 0) +
    (filters.start_time ? 1 : 0);

  const activeAdvancedFilterCount = advancedFilters.filter(f => f.colors.length > 0).length;

  return (
    <div className="hud-panel p-3 flex flex-col gap-2">
      {/* ── Row 1: AutoFill + Clothing + Logic ── */}
      <div className="flex gap-3 items-start">
        {/* ── Image Auto-Fill Zone ── */}
        <div className="flex-shrink-0">
          <SectionLabel>AUTO-FILL</SectionLabel>
          <div
            className={`
              relative w-28 h-[84px] rounded-sm border-2 border-dashed cursor-pointer
              flex flex-col items-center justify-center gap-1 transition-all duration-200 overflow-hidden
              ${isDragOver
                ? "border-pink-400 bg-pink-950/30 scale-[1.02]"
                : autoFillImage
                  ? "border-cyan-500/60 bg-slate-900/60"
                  : "border-slate-700 bg-slate-900/30 hover:border-slate-600 hover:bg-slate-900/50"
              }
            `}
            onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleDrop}
            onClick={() => !autoFillImage && fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileChange}
            />

            {autoFillImage ? (
              <>
                <Image src={autoFillImage} alt="Target" fill className="object-cover opacity-70" />
                <div className="absolute inset-0 bg-slate-950/40" />
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 z-10">
                  {autoFillStatus === "analyzing" && <AnalyzingOverlay />}
                  {autoFillStatus === "done" && autoFillResult && (
                    <DoneOverlay result={autoFillResult} />
                  )}
                  {autoFillStatus === "error" && (
                    <div className="font-mono text-[8px] text-red-400 text-center px-1">ANALYSIS FAILED</div>
                  )}
                </div>
                <button
                  className="absolute top-1 right-1 z-20 w-4 h-4 rounded-full bg-slate-900/80 border border-slate-700 flex items-center justify-center hover:border-red-500/60 hover:text-red-400 text-slate-500 transition-colors"
                  onClick={(e) => { e.stopPropagation(); clearAutoFill(); }}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-2 h-2">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}
                  className={`w-5 h-5 transition-colors ${isDragOver ? "text-pink-400" : "text-slate-600"}`}
                >
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
                </svg>
                <span className={`font-mono text-[8px] text-center leading-tight px-1 transition-colors ${isDragOver ? "text-pink-400" : "text-slate-600"}`}>
                  {isDragOver ? "RELEASE TO ANALYZE" : "DROP TARGET\nIMAGE"}
                </span>
              </>
            )}
          </div>
        </div>

        {/* ── Clothing Chips ── */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-2">
              <SectionLabel>CLOTHING TYPE</SectionLabel>
              <span className="font-mono text-[7px] text-slate-500 italic">(matches ANY item)</span>
            </div>
            <div className="flex items-center gap-1 bg-slate-900/60 border border-slate-800 rounded-sm p-0.5">
              {(["OR", "AND"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => setLogic(l)}
                  className={`
                    px-2 py-0.5 rounded-sm font-mono text-[8px] tracking-wider transition-all
                    ${filters.logic === l
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
          <div className="flex flex-wrap gap-1.5">
            {CLOTHING_OPTIONS.map((item) => {
              const active = filters.clothing.includes(item);
              const isAutoFilled = autoFillResult?.detected_attributes?.class_name === item && autoFillStatus === "done";
              return (
                <button
                  key={item}
                  onClick={() => toggleClothing(item)}
                  className={`
                    relative chip transition-all
                    ${active ? "active" : ""}
                    ${isAutoFilled ? "ring-1 ring-pink-500/60" : ""}
                  `}
                >
                  {item}
                  {isAutoFilled && (
                    <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-pink-500 border border-slate-950 animate-pulse" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Row 2: Color Matrix + Cam/Video + Threshold ── */}
      <div className="flex gap-3 items-start">
        {/* Color Section with Tabs */}
        <div className="flex-1">
          {/* Color Category Tabs */}
          <div className="flex items-center gap-1 mb-1">
            <div className="flex items-center gap-2">
              <SectionLabel>COLOR</SectionLabel>
              <span className="font-mono text-[7px] text-slate-500 italic">(matches ANY item)</span>
            </div>
            <div className="flex items-center gap-0.5 ml-2">
              {(["OR", "AND"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => setLogic(l)}
                  className={`
                    px-2 py-0.5 rounded-sm font-mono text-[8px] tracking-wider transition-all
                    ${filters.logic === l
                      ? "bg-cyan-900/60 text-cyan-400 border border-cyan-700/60"
                      : "text-slate-600 hover:text-slate-400"
                    }
                  `}
                >
                  {l}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-0.5 ml-2">
              {([
                { id: "color", label: "สี" },
                { id: "temp", label: "อุณหภูมิ" },
                { id: "brightness", label: "ความสว่าง" },
                { id: "vibrancy", label: "ความสด" },
              ] as { id: ColorTab; label: string }[]).map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveColorTab(tab.id)}
                  className={`px-2 py-0.5 rounded-sm font-mono text-[8px] transition-all ${
                    activeColorTab === tab.id
                      ? "bg-cyan-900/60 text-cyan-400 border border-cyan-700/60"
                      : "text-slate-600 hover:text-slate-400 border border-transparent"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Color Options based on active tab */}
          <div className="flex flex-wrap gap-1.5 mt-1 relative">
            {activeColorTab === "color" && (
              <div className="flex flex-wrap gap-1.5">
                {TONE_GROUP_OPTIONS.map(({ value, label, color }) => {
                  const detailedColors = TONE_TO_DETAILED_COLORS[value] || [];
                  const allSubColorsSelected = detailedColors.length > 0 && 
                    detailedColors.every(dc => filters.colors.includes(dc.value as any));
                  const someSubColorsSelected = detailedColors.some(dc => filters.colors.includes(dc.value as any));
                  
                  return (
                    <div key={value} className="relative">
                      <button
                        onClick={() => {
                          // Select/deselect all sub-colors when tone group is clicked
                          const subColorValues = detailedColors.map(dc => dc.value as any);
                          if (allSubColorsSelected) {
                            // Deselect all
                            subColorValues.forEach(sc => {
                              if (filters.colors.includes(sc)) {
                                toggleColor(sc);
                              }
                            });
                          } else {
                            // Select all
                            subColorValues.forEach(sc => {
                              if (!filters.colors.includes(sc)) {
                                toggleColor(sc);
                              }
                            });
                          }
                        }}
                        title={value}
                        className={`
                          relative flex items-center gap-1.5 px-2 py-1 rounded-sm border font-mono text-[9px]
                          transition-all duration-150
                          ${allSubColorsSelected
                            ? "border-white/30 bg-white/5 text-white shadow-sm"
                            : someSubColorsSelected
                              ? "border-white/20 bg-white/3 text-white/80"
                              : "border-slate-800 text-slate-600 hover:border-slate-600 hover:text-slate-400"
                          }
                        `}
                        style={allSubColorsSelected ? { borderColor: color + "60", boxShadow: `0 0 8px ${color}30` } : {}}
                      >
                        <span
                          className={`w-3 h-3 rounded-full border flex-shrink-0 transition-all ${allSubColorsSelected ? "scale-110" : "scale-90"}`}
                          style={{
                            background: color,
                            borderColor: allSubColorsSelected ? color : "rgba(255,255,255,0.1)",
                            boxShadow: allSubColorsSelected ? `0 0 6px ${color}80` : "none",
                          }}
                        />
                        <span style={allSubColorsSelected ? { color } : {}}>{label}</span>
                        <span
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedToneGroup(expandedToneGroup === value ? null : value);
                          }}
                          className="ml-auto text-[8px] text-slate-500 hover:text-slate-300 cursor-pointer px-1 select-none"
                        >
                          {expandedToneGroup === value ? "▼" : "▶"}
                        </span>
                      </button>

                      {/* Detailed colors dropdown with absolute positioning and high z-index */}
                      {expandedToneGroup === value && TONE_TO_DETAILED_COLORS[value] && (
                        <div className="absolute top-full left-0 mt-1 z-50 bg-slate-900/95 border border-slate-700 rounded-sm p-2 shadow-xl min-w-[200px]">
                          <div className="flex flex-wrap gap-1">
                            {TONE_TO_DETAILED_COLORS[value].map(({ value: dcValue, label: dcLabel, hex }) => (
                              <button
                                key={dcValue}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleColor(dcValue as any);
                                }}
                                title={dcLabel}
                                className={`
                                  relative flex items-center gap-1 px-1.5 py-0.5 rounded-sm border font-mono text-[8px]
                                  transition-all duration-150
                                  ${filters.colors.includes(dcValue as any)
                                    ? "border-white/30 bg-white/5 text-white"
                                    : "border-slate-800 text-slate-600 hover:border-slate-600"
                                  }
                                `}
                                style={filters.colors.includes(dcValue as any) ? { borderColor: hex + "40" } : {}}
                              >
                                <span
                                  className={`w-2 h-2 rounded-full border flex-shrink-0`}
                                  style={{
                                    background: hex,
                                    borderColor: filters.colors.includes(dcValue as any) ? hex : "rgba(255,255,255,0.1)",
                                  }}
                                />
                                <span style={filters.colors.includes(dcValue as any) ? { color: hex } : {}}>{dcLabel}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {activeColorTab === "temp" && TEMPERATURE_OPTIONS.map(({ value, label, color }) => {
              const active = filters.temperature === value;
              return (
                <button
                  key={value}
                  onClick={() => setTemperature(active ? undefined : value as any)}
                  title={value}
                  className={`
                    relative flex items-center gap-1.5 px-2 py-1 rounded-sm border font-mono text-[9px]
                    transition-all duration-150
                    ${active
                      ? "border-white/30 bg-white/5 text-white shadow-sm"
                      : "border-slate-800 text-slate-600 hover:border-slate-600 hover:text-slate-400"
                    }
                  `}
                  style={active ? { borderColor: color + "60", boxShadow: `0 0 8px ${color}30` } : {}}
                >
                  <span
                    className={`w-3 h-3 rounded-full border flex-shrink-0 transition-all ${active ? "scale-110" : "scale-90"}`}
                    style={{
                      background: color,
                      borderColor: active ? color : "rgba(255,255,255,0.1)",
                      boxShadow: active ? `0 0 6px ${color}80` : "none",
                    }}
                  />
                  <span style={active ? { color } : {}}>{label}</span>
                </button>
              );
            })}

            {activeColorTab === "brightness" && BRIGHTNESS_OPTIONS.map(({ value, label, color }) => {
              const active = filters.brightness === value;
              return (
                <button
                  key={value}
                  onClick={() => setBrightness(active ? undefined : value as any)}
                  title={value}
                  className={`
                    relative flex items-center gap-1.5 px-2 py-1 rounded-sm border font-mono text-[9px]
                    transition-all duration-150
                    ${active
                      ? "border-white/30 bg-white/5 text-white shadow-sm"
                      : "border-slate-800 text-slate-600 hover:border-slate-600 hover:text-slate-400"
                    }
                  `}
                  style={active ? { borderColor: color + "60", boxShadow: `0 0 8px ${color}30` } : {}}
                >
                  <span
                    className={`w-3 h-3 rounded-full border flex-shrink-0 transition-all ${active ? "scale-110" : "scale-90"}`}
                    style={{
                      background: color,
                      borderColor: active ? color : "rgba(255,255,255,0.1)",
                      boxShadow: active ? `0 0 6px ${color}80` : "none",
                    }}
                  />
                  <span style={active ? { color } : {}}>{label}</span>
                </button>
              );
            })}

            {activeColorTab === "vibrancy" && VIBRANCY_OPTIONS.map(({ value, label, color }) => {
              const active = filters.vibrancy === value;
              return (
                <button
                  key={value}
                  onClick={() => setVibrancy(active ? undefined : value as any)}
                  title={value}
                  className={`
                    relative flex items-center gap-1.5 px-2 py-1 rounded-sm border font-mono text-[9px]
                    transition-all duration-150
                    ${active
                      ? "border-white/30 bg-white/5 text-white shadow-sm"
                      : "border-slate-800 text-slate-600 hover:border-slate-600 hover:text-slate-400"
                    }
                  `}
                  style={active ? { borderColor: color + "60", boxShadow: `0 0 8px ${color}30` } : {}}
                >
                  <span
                    className={`w-3 h-3 rounded-full border flex-shrink-0 transition-all ${active ? "scale-110" : "scale-90"}`}
                    style={{
                      background: color,
                      borderColor: active ? color : "rgba(255,255,255,0.1)",
                      boxShadow: active ? `0 0 6px ${color}80` : "none",
                    }}
                  />
                  <span style={active ? { color } : {}}>{label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Camera + Video — same row, right of color matrix */}
        <div className="flex-shrink-0 flex flex-row items-end gap-1.5">
          <div>
            <SectionLabel>CAMERA</SectionLabel>
            <select
              value={filters.camera_id ?? ""}
              onChange={(e) => setCamera(e.target.value || undefined)}
              className="w-24 bg-slate-900/60 border border-slate-700/60 rounded-sm px-2 py-1 font-mono text-[9px] text-slate-300 outline-none focus:border-cyan-700/60 cursor-pointer appearance-none"
            >
              <option value="">ALL</option>
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div>
            <SectionLabel>VIDEO</SectionLabel>
            <select
              value={filters.video_id ?? ""}
              onChange={(e) => setVideo(e.target.value || undefined)}
              className="bg-slate-900/60 border border-slate-700/60 rounded-sm px-2 py-1 font-mono text-[9px] text-slate-300 outline-none focus:border-cyan-700/60 cursor-pointer appearance-none w-36"
            >
              <option value="">{filters.camera_id ? `ALL (${cameraVideos.length})` : "ALL"}</option>
              {cameraVideos.map((v) => (
                <option key={v.id} value={v.id}>{v.filename}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Threshold Slider */}
        <div className="flex-shrink-0 w-32">
          <SectionLabel>COLOR TOLERANCE</SectionLabel>
          <div className="mt-2 px-1">
            <input
              type="range"
              min={0.1}
              max={1.0}
              step={0.05}
              value={filters.threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
              className="w-full h-1 appearance-none bg-slate-800 rounded-full outline-none cursor-pointer
                [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3
                [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-cyan-400
                [&::-webkit-slider-thumb]:shadow-[0_0_6px_rgba(0,245,255,0.6)]
                [&::-webkit-slider-thumb]:cursor-pointer"
            />
            <div className="flex justify-between mt-1">
              <span className="font-mono text-[7px] text-slate-600">LOOSE</span>
              <span className="font-mono text-[9px] text-cyan-400">{Math.round(filters.threshold * 100)}%</span>
              <span className="font-mono text-[7px] text-slate-600">STRICT</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Row 3: Time + Cam/Video + Actions (all inline) ── */}
      <div className="flex items-center gap-2 pt-1 border-t border-slate-800/60 flex-wrap">
        {/* Clock icon */}
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-3.5 h-3.5 text-slate-600 flex-shrink-0">
          <circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" />
        </svg>
        {/* Time range */}
        <input
          type="datetime-local"
          value={filters.start_time?.slice(0, 16) ?? ""}
          onChange={(e) => setTimeRange(e.target.value ? new Date(e.target.value).toISOString() : undefined, filters.end_time)}
          className="bg-slate-900/60 border border-slate-700/60 rounded-sm px-2 py-1 font-mono text-[9px] text-slate-300 outline-none focus:border-cyan-700/60 cursor-pointer"
          style={{ WebkitAppearance: "none", MozAppearance: "textfield", pointerEvents: "auto" }}
          placeholder="Start date"
          onClick={(e) => e.currentTarget.showPicker?.()}
        />
        <span className="font-mono text-[9px] text-slate-600">→</span>
        <input
          type="datetime-local"
          value={filters.end_time?.slice(0, 16) ?? ""}
          onChange={(e) => setTimeRange(filters.start_time, e.target.value ? new Date(e.target.value).toISOString() : undefined)}
          className="bg-slate-900/60 border border-slate-700/60 rounded-sm px-2 py-1 font-mono text-[9px] text-slate-300 outline-none focus:border-cyan-700/60 cursor-pointer"
          style={{ WebkitAppearance: "none", MozAppearance: "textfield", pointerEvents: "auto" }}
          placeholder="End date"
          onClick={(e) => e.currentTarget.showPicker?.()}
        />


        {/* Right-pinned: filter count + advanced search + clear */}
        <div className="ml-auto flex items-center gap-2 flex-shrink-0">
          {activeFilterCount > 0 && !advancedMode && (
            <span className="font-mono text-[8px] text-slate-600">
              {activeFilterCount} FILTER{activeFilterCount !== 1 ? "S" : ""} ACTIVE
            </span>
          )}
          {advancedMode && (
            <span className="font-mono text-[8px] text-cyan-400 bg-cyan-950/30 px-2 py-0.5 rounded-sm border border-cyan-500/30">
              ADVANCED: {activeAdvancedFilterCount} item{activeAdvancedFilterCount !== 1 ? "s" : ""}
            </span>
          )}
          <button
            onClick={openAdvancedModal}
            className={`
              cursor-pointer font-mono text-[8px] font-bold px-3 py-1 rounded-sm border transition-all duration-200
              ${advancedMode
                ? "border-cyan-500/60 bg-cyan-950/30 text-cyan-400 hover:bg-cyan-900/40 hover:border-cyan-400"
                : "border-slate-600 bg-slate-800/40 text-slate-400 hover:bg-slate-700/40 hover:border-slate-500"
              }
            `}
          >
            {advancedMode ? "EDIT ADVANCED" : "ADVANCED SEARCH"}
          </button>
          <button
            onClick={() => {
              if (advancedMode) {
                clearAdvancedFilters();
              }
              resetFilters();
            }}
            className="cursor-pointer font-mono text-[8px] font-bold px-3 py-1 rounded-sm border border-red-500/60 bg-red-950/30 text-red-400 hover:bg-red-900/40 hover:border-red-400 transition-all duration-200"
          >
            CLEAR ALL
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[8px] text-slate-600 tracking-[0.2em] mb-1 uppercase">
      {children}
    </div>
  );
}

function Spinner() {
  return (
    <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

function AnalyzingOverlay() {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-6 h-6">
        <div className="absolute inset-0 border border-cyan-500/60 animate-ping rounded-full" />
        <div className="absolute inset-1 border border-cyan-400 rounded-full" />
      </div>
      <span className="font-mono text-[7px] text-cyan-400 tracking-widest">ANALYZING</span>
      <div className="progress-bar w-14 mt-0.5" />
    </div>
  );
}

function DoneOverlay({ result }: { result: AttributeDetectionResult }) {
  const className = result.detected_attributes?.class_name;
  const color = result.detected_attributes?.color_name;
  const confidence = result.detected_attributes?.confidence;
  return (
    <div className="flex flex-col items-center gap-0.5 bg-slate-950/70 rounded-sm px-2 py-1.5 w-full mx-1">
      <svg viewBox="0 0 24 24" fill="none" stroke="#39ff14" strokeWidth={2.5} className="w-4 h-4">
        <path d="M20 6L9 17l-5-5" />
      </svg>
      <span className="font-mono text-[8px] text-green-400 font-bold">{className}</span>
      <span className="font-mono text-[7px] text-slate-400">{color}</span>
      <span className="font-mono text-[7px] text-cyan-600">{confidence ? Math.round(confidence * 100) : 0}%</span>
    </div>
  );
}
