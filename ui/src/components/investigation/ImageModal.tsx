"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useInvestigation } from "./InvestigationContext";
import type { SearchResult, DetectionItem, DetailedColor } from "@/types";

// Helper to get color hex from color name
const COLOR_HEX_MAP: Record<string, string> = {
  red: "#ef4444", dark_red: "#991b1b", crimson: "#dc143c", scarlet: "#ff2400", maroon: "#800000",
  orange: "#f97316", dark_orange: "#c2410c", amber: "#f59e0b", peach: "#fcd34d", coral: "#fb923c",
  yellow: "#eab308", gold: "#fbbf24", light_yellow: "#fef08a", mustard: "#a16207", khaki: "#ca8a04",
  green: "#22c55e", dark_green: "#166534", light_green: "#86efac", olive: "#65a30d", lime: "#84cc16",
  forest_green: "#14532d", mint: "#6ee7b7", teal: "#14b8a6",
  blue: "#3b82f6", dark_blue: "#1e3a8a", light_blue: "#93c5fd", navy: "#1e3a5f", sky_blue: "#0ea5e9",
  royal_blue: "#4169e1", cobalt: "#0047ab", turquoise: "#40e0d0",
  purple: "#a855f7", dark_purple: "#6b21a8", light_purple: "#d8b4fe", violet: "#8b5cf6", lavender: "#a78bfa",
  magenta: "#d946ef", fuchsia: "#e879f9", plum: "#9333ea",
  brown: "#92400e", dark_brown: "#78350f", light_brown: "#d97706", tan: "#b45309", beige: "#f5f5dc",
  camel: "#c19a6b",
  pink: "#ec4899", light_pink: "#f9a8d4", hot_pink: "#f472b6", rose: "#fb7185", salmon: "#fa8072",
  white: "#ffffff", light_gray: "#d1d5db", silver: "#c0c0c0",
  black: "#000000", dark_gray: "#374151", gray: "#6b7280",
};

// Color category hex mappings
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

// Color group display names
const GROUP_DISPLAY_NAMES: Record<string, string> = {
  warm_colors: "Warm", cool_colors: "Cool", neutral_colors: "Neutral",
  light_colors: "Light", medium_colors: "Medium", dark_colors: "Dark",
  vibrant_colors: "Vibrant", muted_colors: "Muted", pastel_colors: "Pastel",
  common_shirt_colors: "Shirt", common_pants_colors: "Pants",
  formal_colors: "Formal", casual_colors: "Casual",
};

export default function ImageModal() {
  const { state, closeImage, openTrace, setDetectionDetail } = useInvestigation();
  const { imageTarget, detectionDetail } = state;
  const overlayRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [showVideo, setShowVideo] = useState(false);
  const [bboxVisible, setBboxVisible] = useState<Record<string, boolean>>({});
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgNaturalRef = useRef<{ w: number; h: number } | null>(null);
  const [videoPopupOpen, setVideoPopupOpen] = useState(false);
  const popupVideoRef = useRef<HTMLVideoElement>(null);
  const miniPlayerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ isDragging: boolean; startX: number; startY: number; initialLeft: number; initialTop: number } | null>(null);

  // Mini player state
  const [playerPosition, setPlayerPosition] = useState({ left: 20, top: 20 });
  const [isMinimized, setIsMinimized] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playerDimensions, setPlayerDimensions] = useState({ width: 480, height: 300 });
  const resizeRef = useRef<{
    dir: string; startX: number; startY: number;
    initW: number; initH: number; initL: number; initT: number;
  } | null>(null);

  const [imgUrl, setImgUrl] =  useState('');
  
  // State for time offset adjustment
  const [targetOffset, setTargetOffset] = useState<number>(0);

  // Get items early so drawBboxes can reference them
  const items: DetectionItem[] = state.detectionDetail?.items || state.imageTarget?.items || [];
  const sortedItems = [...items].sort((a, b) => {
    const hasTop = items.some(i => i.category === 'TOP');
    const hasBottom = items.some(i => i.category === 'BOTTOM');
    const getPriority = (category: string) => {
      if (hasTop) { if (category === 'TOP') return 0; if (category === 'DRESS') return 1; return 2; }
      else if (hasBottom) { if (category === 'BOTTOM') return 2; if (category === 'DRESS') return 1; return 0; }
      return 0;
    };
    return getPriority(a.category) - getPriority(b.category);
  });

  const toggleBbox = (itemId: string) => {
    setBboxVisible(prev => ({ ...prev, [itemId]: !prev[itemId] }));
  };

  // Draw bboxes on canvas — item bboxes are in full-frame coords; subtract person bbox offset
  const drawBboxes = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    // Sync canvas pixel dimensions to its CSS display size
    const cw = canvas.offsetWidth;
    const ch = canvas.offsetHeight;
    if (!cw || !ch) return;
    canvas.width = cw;
    canvas.height = ch;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, cw, ch);

    const nat = imgNaturalRef.current;
    if (!nat) return;

    // frame-crop API adds 15% padding around person bbox before cropping
    // so the actual image top-left is (cx1, cy1), not (px1, py1)
    const personBbox: number[] = detectionDetail?.bbox || [];
    const px1 = Number(personBbox[0] ?? 0);
    const py1 = Number(personBbox[1] ?? 0);
    const px2 = Number(personBbox[2] ?? 0);
    const py2 = Number(personBbox[3] ?? 0);
    const bw = px2 - px1, bh = py2 - py1;
    const PADDING = 0.15;
    const cx1 = Math.max(0, Math.floor(px1 - bw * PADDING));
    const cy1 = Math.max(0, Math.floor(py1 - bh * PADDING));

    // object-contain scale
    const scale = Math.min(cw / nat.w, ch / nat.h);
    const rw = nat.w * scale, rh = nat.h * scale;
    const ox = (cw - rw) / 2, oy = (ch - rh) / 2;

    sortedItems.forEach(item => {
      if (!bboxVisible[item.id]) return;
      const bbox = item.bbox;
      if (!bbox || bbox.length < 4) return;
      // Convert full-frame → crop-relative by subtracting padded crop origin
      const x1 = bbox[0] - cx1;
      const y1 = bbox[1] - cy1;
      const x2 = bbox[2] - cx1;
      const y2 = bbox[3] - cy1;
      const sx = ox + x1 * scale;
      const sy = oy + y1 * scale;
      const sw = (x2 - x1) * scale;
      const sh = (y2 - y1) * scale;
      ctx.strokeStyle = item.category === 'TOP' ? '#22d3ee' : '#34d399';
      ctx.lineWidth = 2;
      ctx.strokeRect(sx, sy, sw, sh);
      ctx.fillStyle = item.category === 'TOP' ? 'rgba(34,211,238,0.12)' : 'rgba(52,211,153,0.12)';
      ctx.fillRect(sx, sy, sw, sh);
      ctx.font = 'bold 11px monospace';
      ctx.fillStyle = item.category === 'TOP' ? '#22d3ee' : '#34d399';
      ctx.fillText(item.class_name, sx + 4, sy + 14);
    });
  }, [sortedItems, bboxVisible, detectionDetail]);

  useEffect(() => { drawBboxes(); }, [drawBboxes]);

  // Get image URL from detectionDetail or fallback to imageTarget
  const effectiveImageUrl = detectionDetail?.image_url;

  // Initialize targetOffset from API
  useEffect(() => {
    if (detectionDetail?.video_time_offset !== undefined) {
      setTargetOffset(Number(detectionDetail.video_time_offset));
      setShowVideo(true);
    }
    setImgUrl(effectiveImageUrl);
  }, [detectionDetail, imageTarget, effectiveImageUrl]);

  // Keyboard close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") closeImage(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [closeImage]);

  const handleOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === overlayRef.current) closeImage();
    },
    [closeImage]
  );

  const handleDragMove = useCallback((e: MouseEvent) => {
    if (!dragRef.current?.isDragging) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    setPlayerPosition({
      left: Math.max(0, Math.min(window.innerWidth - 200, dragRef.current.initialLeft + dx)),
      top: Math.max(0, Math.min(window.innerHeight - 40, dragRef.current.initialTop + dy)),
    });
  }, []);

  const handleDragEnd = useCallback(() => {
    dragRef.current = null;
    setIsDragging(false);
  }, []);

  const handleResizeMove = useCallback((e: MouseEvent) => {
    if (!resizeRef.current) return;
    const { dir, startX, startY, initW, initH, initL, initT } = resizeRef.current;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    const minW = 280, minH = 180;

    setPlayerDimensions(prev => {
      let w = prev.width, h = prev.height;
      if (dir.includes('e')) w = Math.max(minW, initW + dx);
      if (dir.includes('s')) h = Math.max(minH, initH + dy);
      if (dir.includes('w')) w = Math.max(minW, initW - dx);
      if (dir.includes('n')) h = Math.max(minH, initH - dy);
      return { width: w, height: h };
    });
    setPlayerPosition(prev => {
      let l = prev.left, t = prev.top;
      if (dir.includes('w')) l = Math.max(0, initL + dx);
      if (dir.includes('n')) t = Math.max(0, initT + dy);
      return { left: l, top: t };
    });
  }, []);

  const handleResizeEnd = useCallback(() => {
    resizeRef.current = null;
    setIsResizing(false);
  }, []);

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleDragMove);
      window.addEventListener('mouseup', handleDragEnd);
      return () => {
        window.removeEventListener('mousemove', handleDragMove);
        window.removeEventListener('mouseup', handleDragEnd);
      };
    }
  }, [isDragging, handleDragMove, handleDragEnd]);

  useEffect(() => {
    if (isResizing) {
      window.addEventListener('mousemove', handleResizeMove);
      window.addEventListener('mouseup', handleResizeEnd);
      return () => {
        window.removeEventListener('mousemove', handleResizeMove);
        window.removeEventListener('mouseup', handleResizeEnd);
      };
    }
  }, [isResizing, handleResizeMove, handleResizeEnd]);

  if (!imageTarget) return null;

  const handleOpenTrace = () => {
    closeImage();
    openTrace(imageTarget);
  };

  const openVideo = () => {
    const videoId = detectionDetail?.video_id;

    if (videoId) {
      if (showVideo) {
        const params = new URLSearchParams({
          video: videoId,
          time: targetOffset.toString(), // ใช้ targetOffset ที่ถูกปรับแล้วแทนค่าเดิม
          timestamp: detectionDetail?.timestamp || imageTarget.timestamp,
          camera_id: detectionDetail?.camera_id || imageTarget.camera_id,
          clothing_class: detectionDetail?.class_name || imageTarget.clothing_class,
          color: detectionDetail?.category || imageTarget.color,
          confidence: (detectionDetail?.confidence || imageTarget.confidence)?.toString() || "0",
          play: "true"
        });
        window.open(`/search?${params.toString()}`, '_blank');
      } else {
        setShowVideo(true);
      }
    } else {
      alert('No video available for this detection');
    }
  };

  // ----- Time Offset Management -----
  
  const jumpToTargetOffset = () => {
    if (videoRef.current) {
      videoRef.current.currentTime = targetOffset;
      const playPromise = videoRef.current.play();
      if (playPromise !== undefined) {
        playPromise.catch((error) => {
          if (error.name !== 'AbortError') {
            console.error("Video play error:", error);
          }
        });
      }
    }
  };

  const adjustOffset = (seconds: number) => {
    setTargetOffset(prev => {
      const newOffset = Math.max(0, prev + seconds);
      // Update video currentTime if video is playing in popup
      if (popupVideoRef.current && videoPopupOpen) {
        popupVideoRef.current.currentTime = newOffset;
      }
      // Also update main video if playing
      if (videoRef.current && showVideo) {
        videoRef.current.currentTime = newOffset;
      }
      return newOffset;
    });
  };

  const openVideoPopup = () => {
    setVideoPopupOpen(true);
  };

  const closeVideoPopup = () => {
    setVideoPopupOpen(false);
    if (popupVideoRef.current) {
      popupVideoRef.current.pause();
    }
  };

  // ----- Mini Player Drag & Resize -----

  const handleDragStart = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    dragRef.current = {
      isDragging: true,
      startX: e.clientX,
      startY: e.clientY,
      initialLeft: playerPosition.left,
      initialTop: playerPosition.top,
    };
  };

  const handleResizeStart = (dir: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizing(true);
    resizeRef.current = {
      dir,
      startX: e.clientX,
      startY: e.clientY,
      initW: playerDimensions.width,
      initH: playerDimensions.height,
      initL: playerPosition.left,
      initT: playerPosition.top,
    };
  };

  const togglePlay = () => {
    if (!popupVideoRef.current) return;
    if (popupVideoRef.current.paused) {
      popupVideoRef.current.play().catch(() => {});
      setIsPlaying(true);
    } else {
      popupVideoRef.current.pause();
      setIsPlaying(false);
    }
  };

  const toggleMinimize = () => setIsMinimized(prev => !prev);

  const resetOffset = () => {
    const original = detectionDetail?.video_time_offset;
    if (original === undefined) return;
    const t = Number(original);
    setTargetOffset(t);
    // Seek both video elements and play
    [popupVideoRef.current, videoRef.current].forEach(v => {
      if (!v) return;
      v.currentTime = t;
      v.play().catch(() => {});
    });
    setIsPlaying(true);
  };

  // Color analysis helper - get all colors from items
  const getAllColors = () => {
    const allColors: { color: DetailedColor; percentage: number; item: string }[] = [];
    items.forEach(item => {
      item.colors?.top_colors?.forEach(tc => {
        allColors.push({ color: tc.name, percentage: tc.percentage, item: item.class_name });
      });
    });
    return allColors.sort((a, b) => b.percentage - a.percentage).slice(0, 8);
  };
  
  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/90 backdrop-blur-sm"
      onClick={handleOverlayClick}
      style={{ animation: "fade-in 0.2s ease-out" }}
    >
      <div
        className="relative w-full max-w-[1400px] max-h-[95vh] flex flex-col overflow-hidden bg-slate-900 rounded-lg border border-slate-700 shadow-2xl"
        style={{ animation: "slide-in-up 0.3s ease-out" }}
      >
        {/* Top accent line */}
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-cyan-500 to-transparent" />

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-slate-800/60 flex-shrink-0 bg-slate-950/50">
          <div className="flex items-center gap-4">
            <h2 className="font-orbitron text-lg font-bold text-cyan-400 tracking-[0.15em]">
              DETECTION VIEW
            </h2>
            
            {/* Detection Items Summary */}
            <div className="flex items-center gap-2">
              {sortedItems.length > 0 ? (
                sortedItems.map((item) => (
                  <div key={item.id} className="flex items-center gap-1.5">
                    <span
                      className={`px-2.5 py-1 rounded font-mono text-xs font-bold uppercase tracking-wider
                        ${item.category === "TOP"
                          ? "bg-cyan-950/80 border border-cyan-600/60 text-cyan-300"
                          : "bg-emerald-950/80 border border-emerald-600/60 text-emerald-300"
                        }`}
                    >
                      {item.class_name}
                    </span>
                    <span className="font-mono text-xs text-slate-400">
                      {(item.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                ))
              ) : (
                <span className="px-2.5 py-1 bg-slate-800 border border-slate-600 rounded font-mono text-xs font-bold text-slate-300 uppercase">
                  {detectionDetail?.class_name || imageTarget?.clothing_class || "Unknown"}
                </span>
              )}
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-slate-500">
              {detectionDetail?.camera_name || imageTarget.camera_name}
            </span>
            <button
              onClick={closeImage}
              className="p-2 rounded border border-slate-700 text-slate-500 hover:border-slate-500 hover:text-slate-300 transition-colors"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* ── Main Content ── */}
        <div className="flex flex-col lg:flex-row flex-1 overflow-hidden min-h-0">
          
          {/* Left: Image Display */}
          <div className="relative w-full lg:w-[35%] min-h-[300px] lg:min-h-0 bg-slate-950">
            {imgUrl && imgUrl.trim() !== "" ? (
              <>
                <Image
                  src={imgUrl}
                  alt="Detection"
                  fill
                  className="object-contain p-4"
                  unoptimized
                  priority
                  sizes="(max-width: 1024px) 100vw, 60vw"
                  onLoad={(e) => {
                    const img = e.currentTarget as HTMLImageElement;
                    imgNaturalRef.current = { w: img.naturalWidth, h: img.naturalHeight };
                    drawBboxes();
                  }}
                />
                <canvas
                  ref={canvasRef}
                  className="absolute inset-0 pointer-events-none"
                  style={{ width: '100%', height: '100%' }}
                />
              </>
            ) : (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-center">
                  <div className="animate-pulse text-slate-500 text-sm mb-2">Loading image...</div>
                  <div className="w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin mx-auto" />
                </div>
              </div>
            )}
            {/* Corner brackets */}
            <div className="absolute top-4 left-4 w-6 h-6 border-t-2 border-l-2 border-cyan-500/60" />
            <div className="absolute top-4 right-4 w-6 h-6 border-t-2 border-r-2 border-cyan-500/60" />
            <div className="absolute bottom-4 left-4 w-6 h-6 border-b-2 border-l-2 border-cyan-500/60" />
            <div className="absolute bottom-4 right-4 w-6 h-6 border-b-2 border-r-2 border-cyan-500/60" />

          </div>

          {/* Right: Video & Color Details Panel */}
          <div className="w-full lg:flex-1 border-t lg:border-t-0 lg:border-l border-slate-800/60 bg-slate-950/80 flex flex-col">
            
            {/* Panel Header */}
            <div className="flex border-b border-slate-800/60">
              <div className="flex-1 py-3 px-4 font-mono text-xs font-bold uppercase tracking-wider text-cyan-400 bg-cyan-950/30 border-b-2 border-cyan-500">
                Detection Details
              </div>
            </div>

            {/* Panel Content */}
            <div className="flex-1 overflow-y-auto">
              <div className="p-4 space-y-4">
                  {/* Detection Details Summary */}
                  <div className="bg-slate-900/60 rounded-lg p-3 border border-slate-800">
                    <h4 className="font-mono text-xs text-slate-500 uppercase tracking-wider mb-3">Detection Details</h4>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="px-3 py-2 bg-slate-800/50 rounded col-span-2">
                        <span className="font-mono text-[10px] text-slate-500 uppercase block">Camera</span>
                        <span className="font-mono text-sm text-cyan-400">{detectionDetail?.camera_name || imageTarget.camera_name}</span>
                      </div>
                      <div className="px-3 py-2 bg-slate-800/50 rounded">
                        <span className="font-mono text-[10px] text-slate-500 uppercase block">Timestamp</span>
                        <span className="font-mono text-sm text-slate-200">
                          {new Date(detectionDetail?.timestamp || imageTarget.timestamp).toLocaleString("en-GB")}
                        </span>
                      </div>
                      {detectionDetail?.video_time_offset !== undefined && (
                        <div className="px-3 py-2 bg-slate-800/50 rounded">
                          <span className="font-mono text-[10px] text-slate-500 uppercase block">Time Offset</span>
                          <span className="font-mono text-sm text-purple-400">{targetOffset.toFixed(2)}s</span>
                        </div>
                      )}
                      <div className="px-3 py-2 bg-slate-800/50 rounded">
                        <span className="font-mono text-[10px] text-slate-500 uppercase block">Items</span>
                        <span className="font-mono text-sm text-green-400">{items.length} detected</span>
                      </div>
                    </div>
                  </div>

                  {/* Video Controls - Show when video_time_offset is available */}
                  {detectionDetail?.video_time_offset !== undefined && (
                    <div className="bg-slate-900/60 rounded-lg p-3 border border-slate-800">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => adjustOffset(-1)}
                          className="px-3 py-1.5 bg-slate-800 text-slate-300 font-mono text-xs font-bold rounded hover:bg-slate-700 transition-colors border border-slate-700"
                        >
                          &lt;
                        </button>
                        <button
                          onClick={openVideoPopup}
                          className="flex-1 py-2 bg-purple-600/30 text-purple-300 font-mono text-xs font-bold tracking-wider rounded hover:bg-purple-600/50 transition-colors border border-purple-500/50 flex justify-center items-center gap-2"
                        >
                          <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                            <path d="M8 5v14l11-7z" />
                          </svg>
                          PLAY VIDEO
                        </button>
                        <button
                          onClick={() => adjustOffset(1)}
                          className="px-3 py-1.5 bg-slate-800 text-slate-300 font-mono text-xs font-bold rounded hover:bg-slate-700 transition-colors border border-slate-700"
                        >
                          &gt;
                        </button>
                      </div>
                      <button
                        onClick={resetOffset}
                        className="w-full mt-2 py-1.5 bg-slate-800/50 text-slate-400 font-mono text-[10px] font-bold tracking-wider rounded hover:bg-slate-700/50 transition-colors border border-slate-700/50"
                      >
                        RESET OFFSET
                      </button>
                    </div>
                  )}

                  {/* Per-Item Color Details */}
                  <div className="space-y-3">
                    <h4 className="font-mono text-xs text-slate-500 uppercase tracking-wider">Per-Item Color Breakdown</h4>
                    
                    {sortedItems.length > 0 ? (
                      sortedItems.map((item) => (
                        <div key={item.id} className="bg-slate-900/60 rounded-lg border border-slate-800 overflow-hidden">
                          {/* Item Header */}
                          <div className={`px-3 py-2 flex items-center justify-between
                            ${item.category === 'TOP' ? 'bg-cyan-950/30 border-b border-cyan-800/40' : 'bg-emerald-950/30 border-b border-emerald-800/40'}`}>
                            <div className="flex items-center gap-2">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase
                                ${item.category === 'TOP' ? 'bg-cyan-600/30 text-cyan-300' : 'bg-emerald-600/30 text-emerald-300'}`}>
                                {item.category}
                              </span>
                              <span className="font-mono text-sm font-bold text-slate-200">{item.class_name}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs text-slate-500">conf:</span>
                              <span className={`font-mono text-xs font-bold
                                ${item.confidence >= 0.8 ? 'text-green-400' : item.confidence >= 0.6 ? 'text-yellow-400' : 'text-orange-400'}`}>
                                {(item.confidence * 100).toFixed(1)}%
                              </span>
                              {item.bbox && item.bbox.length >= 4 && (
                                <button
                                  onClick={() => toggleBbox(item.id)}
                                  className={`px-1.5 py-0.5 rounded font-mono text-[9px] font-bold uppercase tracking-wider border transition-colors
                                    ${bboxVisible[item.id]
                                      ? 'bg-cyan-600/30 border-cyan-500/60 text-cyan-300 hover:bg-cyan-600/50'
                                      : 'bg-slate-800/60 border-slate-600/60 text-slate-400 hover:text-slate-200'}`}
                                >
                                  {bboxVisible[item.id] ? 'HIDE' : 'SHOW'} BOX
                                </button>
                              )}
                            </div>
                          </div>

                          <div className="p-3 space-y-3">
                            {/* Primary Color */}
                            {item.colors?.primary_color && (
                              <div className="flex items-center gap-3">
                                <span className="font-mono text-xs text-slate-500 uppercase w-16">Primary</span>
                                <div className="flex items-center gap-2 flex-1">
                                  <div 
                                    className="w-5 h-5 rounded border-2 border-slate-600 shadow-sm"
                                    style={{ backgroundColor: COLOR_HEX_MAP[item.colors.primary_color] || '#94a3b8' }}
                                  />
                                  <span className="font-mono text-sm font-medium" style={{ color: COLOR_HEX_MAP[item.colors.primary_color] || '#94a3b8' }}>
                                    {item.colors.primary_color}
                                  </span>
                                </div>
                              </div>
                            )}

                            {/* Top Colors with Confidence */}
                            {item.colors?.top_colors && item.colors.top_colors.length > 0 && (
                              <div className="space-y-2">
                                <span className="font-mono text-xs text-slate-500 uppercase">Color Distribution</span>
                                <div className="space-y-1.5">
                                  {item.colors.top_colors
                                    .sort((a, b) => b.percentage - a.percentage)
                                    .slice(0, 6)
                                    .map((color, cidx) => (
                                      <div key={cidx} className="flex items-center gap-3">
                                        <div 
                                          className="w-4 h-4 rounded-full border border-slate-600 flex-shrink-0"
                                          style={{ backgroundColor: COLOR_HEX_MAP[color.name] || '#94a3b8' }}
                                        />
                                        <span className="font-mono text-xs text-slate-300 w-24 truncate">{color.name}</span>
                                        <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                                          <div
                                            className="h-full rounded-full transition-all"
                                            style={{
                                              width: `${Math.min(color.percentage, 100)}%`,
                                              backgroundColor: COLOR_HEX_MAP[color.name] || '#94a3b8',
                                            }}
                                          />
                                        </div>
                                        <span className="font-mono text-xs text-cyan-400 w-12 text-right">{color.percentage.toFixed(1)}%</span>
                                      </div>
                                    ))}
                                </div>
                              </div>
                            )}

                            {/* Color Category Groups */}
                            {(item.colors?.brightness_groups || item.colors?.vibrancy_groups || item.colors?.temperature_groups) && (
                              <div className="pt-2 border-t border-slate-800/60">
                                <span className="font-mono text-xs text-slate-500 uppercase block mb-2">Color Properties</span>
                                <div className="grid grid-cols-3 gap-2">
                                  {item.colors.temperature_groups && Object.entries(item.colors.temperature_groups)
                                    .filter(([_, val]) => val > 0)
                                    .map(([name, val]) => (
                                      <div key={name} className="flex items-center gap-1.5 px-2 py-1 bg-slate-800/50 rounded">
                                        <div className="w-2 h-2 rounded" style={{ backgroundColor: CATEGORY_HEX_MAP[name] }} />
                                        <span className="font-mono text-[10px] text-slate-400">{GROUP_DISPLAY_NAMES[name]}</span>
                                        <span className="font-mono text-[10px] text-slate-300 ml-auto">{(val as number).toFixed(0)}%</span>
                                      </div>
                                    ))}
                                  {item.colors.brightness_groups && Object.entries(item.colors.brightness_groups)
                                    .filter(([_, val]) => val > 0)
                                    .map(([name, val]) => (
                                      <div key={name} className="flex items-center gap-1.5 px-2 py-1 bg-slate-800/50 rounded">
                                        <div className="w-2 h-2 rounded" style={{ backgroundColor: CATEGORY_HEX_MAP[name] }} />
                                        <span className="font-mono text-[10px] text-slate-400">{GROUP_DISPLAY_NAMES[name]}</span>
                                        <span className="font-mono text-[10px] text-slate-300 ml-auto">{(val as number).toFixed(0)}%</span>
                                      </div>
                                    ))}
                                  {item.colors.vibrancy_groups && Object.entries(item.colors.vibrancy_groups)
                                    .filter(([_, val]) => val > 0)
                                    .map(([name, val]) => (
                                      <div key={name} className="flex items-center gap-1.5 px-2 py-1 bg-slate-800/50 rounded">
                                        <div className="w-2 h-2 rounded" style={{ backgroundColor: CATEGORY_HEX_MAP[name] }} />
                                        <span className="font-mono text-[10px] text-slate-400">{GROUP_DISPLAY_NAMES[name]}</span>
                                        <span className="font-mono text-[10px] text-slate-300 ml-auto">{(val as number).toFixed(0)}%</span>
                                      </div>
                                    ))}
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="text-center py-8 text-slate-500">
                        <p className="font-mono text-sm">No detailed color data available</p>
                      </div>
                    )}
                  </div>
                </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Mini Player (desktop-style resizable window) ── */}
      {videoPopupOpen && detectionDetail?.video_id && (
        <div
          ref={miniPlayerRef}
          className="fixed z-[60] bg-slate-900 border border-slate-600 shadow-2xl select-none"
          style={{
            left: playerPosition.left,
            top: playerPosition.top,
            width: playerDimensions.width,
            height: isMinimized ? 36 : playerDimensions.height,
            minWidth: 280,
            minHeight: isMinimized ? 36 : 180,
          }}
        >
          {/* ── Title bar (drag handle) ── */}
          <div
            className="flex items-center justify-between h-9 px-2 bg-slate-950 border-b border-slate-700 cursor-move"
            onMouseDown={handleDragStart}
          >
            {/* Left: offset */}
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-[11px] text-slate-400">Offset: <span className="text-purple-400">{targetOffset.toFixed(2)}s</span></span>
            </div>

            {/* Right: window controls */}
            <div className="flex items-center" onMouseDown={e => e.stopPropagation()}>
              <button onClick={toggleMinimize} className="w-7 h-7 flex items-center justify-center text-slate-500 hover:text-white hover:bg-slate-700 transition-colors" title={isMinimized ? "Restore" : "Minimize"}>
                {isMinimized
                  ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3.5 h-3.5"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>
                  : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3.5 h-3.5"><path d="M18 12H6"/></svg>
                }
              </button>
              <button onClick={closeVideoPopup} className="w-7 h-7 flex items-center justify-center text-slate-500 hover:text-white hover:bg-red-700 transition-colors" title="Close">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3.5 h-3.5"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
          </div>

          {/* ── Video + controls ── */}
          {!isMinimized && (
            <div className="flex flex-col" style={{ height: 'calc(100% - 36px)' }}>
              {/* Video */}
              <div className="flex-1 bg-black overflow-hidden">
                <video
                  ref={popupVideoRef}
                  controls
                  className="w-full h-full"
                  src={detectionDetail.storage_mode === "json"
                    ? `/api/json/jobs/${detectionDetail.video_id}/video`
                    : `/api/video/videos/${detectionDetail.video_id}/stream`}
                  onLoadedMetadata={() => {
                    if (popupVideoRef.current) {
                      popupVideoRef.current.currentTime = targetOffset;
                    }
                  }}
                  onPlay={() => setIsPlaying(true)}
                  onPause={() => setIsPlaying(false)}
                />
              </div>

              {/* Offset bar */}
              <div className="flex flex-col gap-1 px-2 py-1.5 bg-slate-950/80 border-t border-slate-800">
                <div className="flex items-center gap-1.5">
                  <button onClick={() => adjustOffset(-1)} className="px-2 py-0.5 bg-slate-800 border border-slate-700 font-mono text-[10px] text-slate-300 hover:bg-slate-700 rounded">-1s</button>
                  <button onClick={resetOffset} className="flex-1 py-0.5 bg-slate-800/60 border border-slate-700 font-mono text-[10px] text-slate-400 hover:bg-slate-700 rounded tracking-widest">RESET</button>
                  <button onClick={() => adjustOffset(1)} className="px-2 py-0.5 bg-slate-800 border border-slate-700 font-mono text-[10px] text-slate-300 hover:bg-slate-700 rounded">+1s</button>
                </div>
                <button
                  onClick={togglePlay}
                  className={`w-full py-1 rounded font-mono text-[10px] font-bold tracking-widest flex items-center justify-center gap-1.5 border transition-colors
                    ${isPlaying
                      ? "bg-purple-900/60 border-purple-700/60 text-purple-300 hover:bg-purple-800/60"
                      : "bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700"
                    }`}
                >
                  {isPlaying ? (
                    <><svg viewBox="0 0 24 24" fill="currentColor" className="w-3 h-3"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>PAUSE</>
                  ) : (
                    <><svg viewBox="0 0 24 24" fill="currentColor" className="w-3 h-3"><path d="M8 5v14l11-7z"/></svg>PLAY</>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* ── Resize handles (8 directions) ── */}
          {!isMinimized && (<>
            {/* Edges */}
            <div className="absolute top-9 left-0 w-1.5 bottom-0 cursor-w-resize hover:bg-cyan-500/20" onMouseDown={handleResizeStart('w')} />
            <div className="absolute top-9 right-0 w-1.5 bottom-0 cursor-e-resize hover:bg-cyan-500/20" onMouseDown={handleResizeStart('e')} />
            <div className="absolute top-9 left-0 right-0 h-1.5 cursor-n-resize hover:bg-cyan-500/20" onMouseDown={handleResizeStart('n')} />
            <div className="absolute bottom-0 left-0 right-0 h-1.5 cursor-s-resize hover:bg-cyan-500/20" onMouseDown={handleResizeStart('s')} />
            {/* Corners */}
            <div className="absolute top-9 left-0 w-3 h-3 cursor-nw-resize" onMouseDown={handleResizeStart('nw')} />
            <div className="absolute top-9 right-0 w-3 h-3 cursor-ne-resize" onMouseDown={handleResizeStart('ne')} />
            <div className="absolute bottom-0 left-0 w-3 h-3 cursor-sw-resize" onMouseDown={handleResizeStart('sw')} />
            <div className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize flex items-end justify-end p-0.5" onMouseDown={handleResizeStart('se')}>
              <svg viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-2.5 h-2.5 text-slate-600">
                <path d="M9 3L3 9M9 6L6 9"/>
              </svg>
            </div>
          </>)}
        </div>
      )}
    </div>
  );
}