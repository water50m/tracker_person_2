"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useInvestigation } from "./InvestigationContext";
import type { SearchResult } from "@/types";
import { COLOR_HEX_MAP } from "@/lib/color-utils";

// ─── Helpers ─────────────────────────────────────────────────

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }).toUpperCase();
}

function confidenceColor(c: number) {
  if (c >= 0.9) return { text: "text-green-400", bg: "bg-green-500/20", border: "border-green-500/40" };
  if (c >= 0.75) return { text: "text-cyan-400", bg: "bg-cyan-500/20", border: "border-cyan-500/40" };
  if (c >= 0.6) return { text: "text-yellow-400", bg: "bg-yellow-500/20", border: "border-yellow-500/40" };
  return { text: "text-red-400", bg: "bg-red-500/20", border: "border-red-500/40" };
}

const CAMERA_COLORS: Record<string, string> = {
  "CAM-01": "text-cyan-400",
  "CAM-02": "text-pink-400",
  "CAM-03": "text-yellow-400",
  "CAM-04": "text-purple-400",
};


// ─── Component ───────────────────────────────────────────────

export default function ResultsGrid() {
  const { state, loadMore, openTrace, openImage } = useInvestigation();
  const { results, total, hasMore, isSearching, isLoadingMore, filters } = state;

  // Infinite scroll sentinel
  const sentinelRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!sentinelRef.current || !hasMore) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isLoadingMore) loadMore();
      },
      { threshold: 0.1 }
    );
    obs.observe(sentinelRef.current);
    return () => obs.disconnect();
  }, [hasMore, isLoadingMore, loadMore]);

  return (
    <div className="hud-panel flex flex-col min-h-0 overflow-hidden">
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800/60 flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="font-orbitron text-[10px] font-bold text-slate-400 tracking-[0.2em]">
            RESULTS
          </span>
          {!isSearching && (
            <span className="font-mono text-[9px] text-cyan-400">
              {total.toLocaleString()} MATCHES
            </span>
          )}
          {isSearching && (
            <span className="font-mono text-[9px] text-slate-600 italic">
              — SEARCHING —
            </span>
          )}
        </div>

        {/* Sort/View controls */}
        <div className="flex items-center gap-2">
          <span className="font-mono text-[8px] text-slate-600">SORT:</span>
          <button className="font-mono text-[8px] text-cyan-400 hover:text-cyan-300">CONFIDENCE ↓</button>
          <div className="w-px h-3 bg-slate-800" />
          <GridSizeToggle />
        </div>
      </div>

      {/* ── Grid ── */}
      <div
        ref={gridRef}
        className="flex-1 overflow-y-auto p-3 min-h-0"
      >
        {isSearching ? (
          <SkeletonGrid />
        ) : results.length === 0 ? (
          <EmptyState hasFilters={filters.clothing.length > 0 || filters.colors.length > 0} />
        ) : (
          <>
            <div className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(100px,1fr))] transition-opacity">
              {results.map((result, i) => (
                <ResultCard
                  key={`${result.id}-${i}`}
                  result={result}
                  index={i}
                  onClick={() => openImage(result)}
                />
              ))}
            </div>

            {/* Infinite scroll sentinel */}
            {hasMore && (
              <div ref={sentinelRef} className="py-4 flex justify-center">
                {isLoadingMore ? (
                  <LoadingMoreIndicator />
                ) : (
                  <div className="font-mono text-[9px] text-slate-700">SCROLL FOR MORE</div>
                )}
              </div>
            )}

            {/* End of results */}
            {!hasMore && results.length > 0 && (
              <div className="py-4 flex items-center gap-3">
                <div className="flex-1 h-px bg-slate-800" />
                <span className="font-mono text-[8px] text-slate-700 tracking-widest">
                  END OF RESULTS · {total} TOTAL
                </span>
                <div className="flex-1 h-px bg-slate-800" />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ─── ResultCard ───────────────────────────────────────────────

function ResultCard({
  result,
  index,
  onClick,
}: {
  result: SearchResult;
  index: number;
  onClick: () => void;
}) {
  const [loaded, setLoaded] = useState(false);
  const conf = confidenceColor(result.confidence);
  const topColors = result.all_top_colors || result.top_colors || [];
  const items = result.items || [];

  const thumbnailUrl = typeof result.thumbnail_url === "string" ? result.thumbnail_url : "";
  const hasThumbnail = thumbnailUrl && thumbnailUrl.trim().length > 0;
  return (
    <div
      className="relative group cursor-pointer rounded-sm overflow-hidden border border-slate-800/60
        hover:border-cyan-500/40 transition-all duration-200
        hover:shadow-[0_0_15px_rgba(0,245,255,0.1)]"
      style={{
        aspectRatio: "2/3",
        animationDelay: `${Math.min(index * 30, 300)}ms`,
        animation: "fade-in 0.3s ease-out forwards",
      }}
      onClick={onClick}
    >
      {/* Thumbnail */}
      <div className="absolute inset-0 bg-slate-900">
        {hasThumbnail ? (
          <>
            {!loaded && <ThumbnailSkeleton />}
            <Image
              src={thumbnailUrl}
              alt={result.clothing_class}
              fill
              className={`object-cover transition-all duration-300 ${loaded ? "opacity-100" : "opacity-0"}`}
              onLoad={() => setLoaded(true)}
              unoptimized
            />
          </>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="font-mono text-[9px] text-slate-700">NO IMAGE</span>
          </div>
        )}
      </div>

      {/* Scanline */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,0,0,0.07) 3px,rgba(0,0,0,0.07) 4px)",
        }}
      />

      {/* Track ID (top-left) */}
      {result.track_id != null && (
        <div className="absolute top-1 left-1 px-1 py-0.5 rounded-sm bg-slate-950/70 border border-slate-700/60 font-mono text-[8px] font-bold text-slate-300">
          #{result.track_id}
        </div>
      )}

      {/* Frame number (top-right) */}
      {result.frame != null && (
        <div className="absolute top-1 right-1 px-1 py-0.5 rounded-sm bg-slate-950/70 border border-slate-700/60 font-mono text-[8px] font-bold text-slate-300">
          f{result.frame}
        </div>
      )}

      {/* Bottom overlay: class + color — always visible */}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-950/90 via-slate-950/60 to-transparent pt-4 pb-1.5 px-1.5">
        <div className="flex flex-col gap-0.5">
          {items.length > 0 ? (
            items.slice(0, 2).map((item) => (
              <div key={item.id} className="flex items-center gap-1 min-w-0">
                <span className="font-mono text-[7px] font-bold text-white/90 shrink-0">
                  {item.class_name}
                </span>
                <div className="flex gap-0.5 flex-wrap">
                  {(item.colors?.top_colors || []).map((c: any, i: number) => (
                    <div
                      key={i}
                      className="w-2 h-2 rounded-full ring-1 ring-black/40"
                      style={{ backgroundColor: COLOR_HEX_MAP[c.name] || "#94a3b8" }}
                      title={`${c.name}: ${Math.round(c.percentage)}%`}
                    />
                  ))}
                </div>
              </div>
            ))
          ) : (
            <div className="flex items-center gap-1 min-w-0">
              <span className="font-mono text-[7px] font-bold text-white/90 shrink-0">
                {result.clothing_class}
              </span>
              <div className="flex gap-0.5 flex-wrap">
                {topColors.map((c: any, i: number) => (
                  <div
                    key={i}
                    className="w-2 h-2 rounded-full ring-1 ring-black/40"
                    style={{ backgroundColor: COLOR_HEX_MAP[c.name] || "#94a3b8" }}
                    title={`${c.name}: ${Math.round(c.percentage)}%`}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="font-mono text-[6px] text-slate-500 mt-0.5">
          {formatDate(result.timestamp)} {formatTime(result.timestamp)}
        </div>
      </div>

    </div>
  );
}

// ─── Skeleton states ─────────────────────────────────────────

function SkeletonGrid() {
  return (
    <div className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(100px,1fr))]">
      {Array.from({ length: 24 }).map((_, i) => (
        <div
          key={i}
          className="relative rounded-sm overflow-hidden bg-slate-900/60 border border-slate-800/40 animate-pulse"
          style={{ aspectRatio: "2/3", animationDelay: `${i * 40}ms` }}
        >
          <div className="absolute inset-0 bg-gradient-to-t from-slate-800/40 to-transparent" />
          {/* Scan effect */}
          <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-transparent via-cyan-500/40 to-transparent animate-[scan-line_2s_linear_infinite]" />
        </div>
      ))}
    </div>
  );
}

function ThumbnailSkeleton() {
  return (
    <div className="absolute inset-0 bg-slate-900 animate-pulse">
      <div className="absolute inset-0 bg-gradient-to-t from-slate-800/40 to-transparent" />
    </div>
  );
}

function EmptyState({ hasFilters }: { hasFilters: boolean }) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-4 py-12">
      {/* Icon */}
      <div className="relative">
        <div className="w-16 h-16 border border-slate-800 rounded-full flex items-center justify-center">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-7 h-7 text-slate-700">
            <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
          </svg>
        </div>
        <div className="absolute -inset-2 border border-dashed border-slate-800 rounded-full animate-[spin_12s_linear_infinite]" />
      </div>
      <div className="text-center space-y-1">
        <p className="font-orbitron text-[11px] text-slate-600 tracking-[0.2em]">
          {hasFilters ? "NO MATCHES FOUND" : "NO RESULTS"}
        </p>
        <p className="font-mono text-[9px] text-slate-700">
          {hasFilters
            ? "Try loosening the color tolerance or changing filters"
            : "Set filters and press SEARCH"}
        </p>
      </div>
    </div>
  );
}

function LoadingMoreIndicator() {
  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="w-1 h-1 rounded-full bg-cyan-600 animate-bounce"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </div>
      <span className="font-mono text-[9px] text-slate-600 tracking-widest">LOADING</span>
    </div>
  );
}

function GridSizeToggle() {
  const [size, setSize] = useState<"sm" | "md" | "lg">("md");
  return (
    <div className="flex items-center gap-1">
      {(["sm", "md", "lg"] as const).map((s) => (
        <button
          key={s}
          onClick={() => setSize(s)}
          className={`p-0.5 rounded-sm transition-colors ${size === s ? "text-cyan-400" : "text-slate-700 hover:text-slate-500"}`}
        >
          {s === "sm" && (
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3 h-3">
              <rect x="1" y="1" width="3" height="3" /><rect x="5" y="1" width="3" height="3" />
              <rect x="9" y="1" width="3" height="3" /><rect x="13" y="1" width="2" height="3" />
              <rect x="1" y="5" width="3" height="3" /><rect x="5" y="5" width="3" height="3" />
              <rect x="9" y="5" width="3" height="3" /><rect x="13" y="5" width="2" height="3" />
            </svg>
          )}
          {s === "md" && (
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3 h-3">
              <rect x="1" y="1" width="6" height="6" /><rect x="9" y="1" width="6" height="6" />
              <rect x="1" y="9" width="6" height="6" /><rect x="9" y="9" width="6" height="6" />
            </svg>
          )}
          {s === "lg" && (
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3 h-3">
              <rect x="1" y="1" width="14" height="6" /><rect x="1" y="9" width="14" height="6" />
            </svg>
          )}
        </button>
      ))}
    </div>
  );
}