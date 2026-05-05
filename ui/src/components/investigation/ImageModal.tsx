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
  const [activeTab, setActiveTab] = useState<'colors' | 'details'>('colors');
  const [videoPopupOpen, setVideoPopupOpen] = useState(false);
  const popupVideoRef = useRef<HTMLVideoElement>(null);
  const miniPlayerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ isDragging: boolean; startX: number; startY: number; initialLeft: number; initialTop: number } | null>(null);

  // Mini player state
  const [playerPosition, setPlayerPosition] = useState({ x: 20, y: 20 }); // bottom-left default (x from left, y from bottom)
  const [playerSize, setPlayerSize] = useState<'small' | 'medium' | 'large' | 'custom'>('large');
  const [isMinimized, setIsMinimized] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);

  // Custom dimensions for mouse resize
  const [playerDimensions, setPlayerDimensions] = useState({ width: 480, height: 270 });
  const resizeRef = useRef<{ isResizing: boolean; startX: number; startY: number; initialWidth: number; initialHeight: number } | null>(null);

  const [imgUrl, setImgUrl] =  useState('');
  
  // State for time offset adjustment
  const [targetOffset, setTargetOffset] = useState<number>(0);

  // Get items from detectionDetail or fallback to imageTarget
  const items: DetectionItem[] = detectionDetail?.items || imageTarget?.items || [];

  // Sort items: TOP first if exists, BOTTOM last if exists, DRESS positioned accordingly
  const sortedItems = [...items].sort((a, b) => {
    const hasTop = items.some(i => i.category === 'TOP');
    const hasBottom = items.some(i => i.category === 'BOTTOM');

    const getPriority = (category: string) => {
      if (hasTop) {
        // TOP first, then DRESS, then others
        if (category === 'TOP') return 0;
        if (category === 'DRESS') return 1;
        return 2;
      } else if (hasBottom) {
        // Others first, then DRESS, then BOTTOM last
        if (category === 'BOTTOM') return 2;
        if (category === 'DRESS') return 1;
        return 0;
      }
      return 0;
    };

    return getPriority(a.category) - getPriority(b.category);
  });

  // Get image URL from detectionDetail or fallback to imageTarget
  const effectiveImageUrl = detectionDetail?.image_url;

  // Initialize targetOffset from API
  useEffect(() => {
    console.log('[ImageModal] detectionDetail:', detectionDetail);
    console.log('[ImageModal] video_time_offset:', detectionDetail?.video_time_offset);
    if (detectionDetail?.video_time_offset !== undefined) {
      console.log('[ImageModal] Setting targetOffset to:', Number(detectionDetail.video_time_offset));
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
    const dx = dragRef.current.startX - e.clientX;
    const dy = e.clientY - dragRef.current.startY;
    setPlayerPosition({
      x: Math.max(0, Math.min(window.innerWidth - 320, dragRef.current.initialLeft + dx)),
      y: Math.max(0, Math.min(window.innerHeight - 200, dragRef.current.initialTop + dy)),
    });
  }, []);

  const handleDragEnd = useCallback(() => {
    dragRef.current = null;
    setIsDragging(false);
  }, []);

  const handleResizeMove = useCallback((e: MouseEvent) => {
    if (!resizeRef.current?.isResizing) return;
    const dx = e.clientX - resizeRef.current.startX;
    const dy = e.clientY - resizeRef.current.startY;
    setPlayerDimensions({
      width: Math.max(200, Math.min(window.innerWidth - 100, resizeRef.current.initialWidth + dx)),
      height: Math.max(120, Math.min(window.innerHeight - 100, resizeRef.current.initialHeight + dy)),
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
    if ((e.target as HTMLElement).closest('.mini-player-controls')) return;
    e.preventDefault();
    setIsDragging(true);
    dragRef.current = {
      isDragging: true,
      startX: e.clientX,
      startY: e.clientY,
      initialLeft: playerPosition.x,
      initialTop: playerPosition.y,
    };
  };

  // ----- Resize Handlers -----

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizing(true);
    setPlayerSize('custom');
    resizeRef.current = {
      isResizing: true,
      startX: e.clientX,
      startY: e.clientY,
      initialWidth: playerDimensions.width,
      initialHeight: playerDimensions.height,
    };
  };

  const toggleMinimize = () => {
    setIsMinimized(prev => !prev);
  };

  const cycleSize = () => {
    setPlayerSize(prev => {
      if (prev === 'small') {
        setPlayerDimensions({ width: 320, height: 180 });
        return 'medium';
      }
      if (prev === 'medium') {
        setPlayerDimensions({ width: 480, height: 270 });
        return 'large';
      }
      setPlayerDimensions({ width: 240, height: 135 });
      return 'small';
    });
  };

  const getPlayerStyle = () => {
    if (isMinimized) {
      const minWidths = { small: 200, medium: 240, large: 320, custom: Math.max(200, playerDimensions.width) };
      return { width: minWidths[playerSize], height: 36 };
    }
    if (playerSize === 'custom') {
      return { width: playerDimensions.width, height: playerDimensions.height };
    }
    const sizes = {
      small: { width: 240, height: 135 },
      medium: { width: 320, height: 180 },
      large: { width: 480, height: 270 },
    };
    return sizes[playerSize as keyof typeof sizes] || sizes.large;
  };

  const resetOffset = () => {
    if (detectionDetail?.video_time_offset !== undefined) {
      setTargetOffset(Number(detectionDetail.video_time_offset));
    }
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
          <div className="relative flex-1 min-h-[300px] lg:min-h-0 bg-slate-950">
            {imgUrl && imgUrl.trim() !== "" ? (
              <Image
                src={imgUrl}
                alt="Detection"
                fill
                className="object-contain p-4"
                unoptimized
                priority
                sizes="(max-width: 1024px) 100vw, 60vw"
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-center">
                  <div className="animate-pulse text-slate-500 text-sm mb-2">Loading image...</div>
                  <div className="w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin mx-auto" />
                </div>
              </div>
            )}
            {/* Scan line overlay */}
            <div className="absolute inset-0 pointer-events-none opacity-30"
              style={{ background: "repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.15) 2px,rgba(0,0,0,0.15) 4px)" }} />
            {/* Corner brackets */}
            <div className="absolute top-4 left-4 w-6 h-6 border-t-2 border-l-2 border-cyan-500/60" />
            <div className="absolute top-4 right-4 w-6 h-6 border-t-2 border-r-2 border-cyan-500/60" />
            <div className="absolute bottom-4 left-4 w-6 h-6 border-b-2 border-l-2 border-cyan-500/60" />
            <div className="absolute bottom-4 right-4 w-6 h-6 border-b-2 border-r-2 border-cyan-500/60" />
          </div>

          {/* Right: Video & Color Details Panel */}
          <div className="w-full lg:w-[480px] xl:w-[520px] border-t lg:border-t-0 lg:border-l border-slate-800/60 bg-slate-950/80 flex flex-col">
            
            {/* Tabs */}
            <div className="flex border-b border-slate-800/60">
              <button
                onClick={() => setActiveTab('colors')}
                className={`flex-1 py-3 px-4 font-mono text-xs font-bold uppercase tracking-wider transition-colors
                  ${activeTab === 'colors' 
                    ? 'text-cyan-400 bg-cyan-950/30 border-b-2 border-cyan-500' 
                    : 'text-slate-500 hover:text-slate-300'}`}
              >
                Color Analysis
              </button>
              <button
                onClick={() => setActiveTab('details')}
                className={`flex-1 py-3 px-4 font-mono text-xs font-bold uppercase tracking-wider transition-colors
                  ${activeTab === 'details' 
                    ? 'text-cyan-400 bg-cyan-950/30 border-b-2 border-cyan-500' 
                    : 'text-slate-500 hover:text-slate-300'}`}
              >
                Detection Details
              </button>
            </div>

            {/* Tab Content */}
            <div className="flex-1 overflow-y-auto">
              {activeTab === 'colors' ? (
                <div className="p-4 space-y-4">
                  {/* Detection Details Summary */}
                  <div className="bg-slate-900/60 rounded-lg p-3 border border-slate-800">
                    <h4 className="font-mono text-xs text-slate-500 uppercase tracking-wider mb-3">Detection Details</h4>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="px-3 py-2 bg-slate-800/50 rounded">
                        <span className="font-mono text-[10px] text-slate-500 uppercase block">Camera</span>
                        <span className="font-mono text-sm text-cyan-400">{detectionDetail?.camera_name || imageTarget.camera_name}</span>
                      </div>
                      {detectionDetail?.video_time_offset !== undefined ? (
                        <>
                          <div className="px-3 py-2 bg-slate-800/50 rounded col-span-1">
                            <span className="font-mono text-[10px] text-slate-500 uppercase block">Time Offset</span>
                            <span className="font-mono text-sm text-purple-400">{targetOffset.toFixed(2)}s</span>
                          </div>
                          <div className="px-3 py-2 bg-slate-800/50 rounded col-span-1">
                            <span className="font-mono text-[10px] text-slate-500 uppercase block">Items</span>
                            <span className="font-mono text-sm text-green-400">{items.length} detected</span>
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="px-3 py-2 bg-slate-800/50 rounded">
                            <span className="font-mono text-[10px] text-slate-500 uppercase block">Time</span>
                            <span className="font-mono text-sm text-slate-200">
                              {new Date(detectionDetail?.timestamp || imageTarget.timestamp).toLocaleTimeString("en-GB")}
                            </span>
                          </div>
                          <div className="px-3 py-2 bg-slate-800/50 rounded">
                            <span className="font-mono text-[10px] text-slate-500 uppercase block">Date</span>
                            <span className="font-mono text-sm text-slate-200">
                              {new Date(detectionDetail?.timestamp || imageTarget.timestamp).toLocaleDateString("en-GB")}
                            </span>
                          </div>
                          <div className="px-3 py-2 bg-slate-800/50 rounded">
                            <span className="font-mono text-[10px] text-slate-500 uppercase block">Items</span>
                            <span className="font-mono text-sm text-green-400">{items.length} detected</span>
                          </div>
                        </>
                      )}
                    </div>

                    {/* Video Controls - Show when video_time_offset is available */}
                    {detectionDetail?.video_time_offset !== undefined && (
                      <div className="mt-3 pt-3 border-t border-slate-800/60">
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
                  </div>

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
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono text-xs text-slate-500">conf:</span>
                              <span className={`font-mono text-xs font-bold
                                ${item.confidence >= 0.8 ? 'text-green-400' : item.confidence >= 0.6 ? 'text-yellow-400' : 'text-orange-400'}`}>
                                {(item.confidence * 100).toFixed(1)}%
                              </span>
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
              ) : (
                <div className="p-4 space-y-4">
                  {/* Detection Details */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-slate-900/60 rounded-lg p-3 border border-slate-800">
                      <span className="font-mono text-xs text-slate-500 uppercase block mb-1">Camera</span>
                      <p className="font-mono text-cyan-400 font-bold">{detectionDetail?.camera_name || imageTarget.camera_name}</p>
                    </div>
                    <div className="bg-slate-900/60 rounded-lg p-3 border border-slate-800">
                      <span className="font-mono text-xs text-slate-500 uppercase block mb-1">Timestamp</span>
                      <p className="font-mono text-slate-200 text-sm">
                        {new Date(detectionDetail?.timestamp || imageTarget.timestamp).toLocaleString("en-GB")}
                      </p>
                    </div>
                  </div>

                  {/* Video Section */}
                  {detectionDetail?.video_id && (
                    <div className="bg-slate-900/60 rounded-lg border border-slate-800 overflow-hidden">
                      <div className="px-3 py-2 bg-purple-950/20 border-b border-purple-800/40 flex items-center justify-between">
                        <span className="font-mono text-xs text-purple-300 uppercase tracking-wider">Video Playback</span>
                        <button
                          onClick={() => setShowVideo(!showVideo)}
                          className="font-mono text-xs text-slate-400 hover:text-white transition-colors"
                        >
                          {showVideo ? 'Hide' : 'Show'}
                        </button>
                      </div>
                      
                      {showVideo && (
                        <div className="p-3 space-y-3">
                          {/* Video Player */}
                          <div className="relative aspect-video bg-black rounded overflow-hidden">
                            <video
                              ref={videoRef}
                              controls
                              className="w-full h-full"
                              src={`/api/video/videos/${detectionDetail.video_id}/stream`}
                              onLoadedMetadata={() => {
                                if (videoRef.current && detectionDetail?.video_time_offset !== undefined) {
                                  videoRef.current.currentTime = Number(detectionDetail.video_time_offset);
                                }
                              }}
                            />
                          </div>

                          {/* Time Controls */}
                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="font-mono text-xs text-slate-500">Target Offset</span>
                              <span className="font-mono text-lg font-bold text-purple-400">{targetOffset.toFixed(2)}s</span>
                            </div>
                            
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => adjustOffset(-1)}
                                className="px-3 py-1.5 bg-slate-800 text-slate-300 font-mono text-xs font-bold rounded hover:bg-slate-700 transition-colors border border-slate-700"
                              >
                                -1s
                              </button>
                              <button
                                onClick={resetOffset}
                                className="flex-1 py-1.5 bg-purple-900/40 text-purple-400 font-mono text-xs font-bold tracking-wider rounded hover:bg-purple-800/60 transition-colors border border-purple-700/50"
                              >
                                RESET
                              </button>
                              <button
                                onClick={() => adjustOffset(1)}
                                className="px-3 py-1.5 bg-slate-800 text-slate-300 font-mono text-xs font-bold rounded hover:bg-slate-700 transition-colors border border-slate-700"
                              >
                                +1s
                              </button>
                            </div>

                            <button
                              onClick={jumpToTargetOffset}
                              className="w-full py-2 bg-purple-600/30 text-purple-300 font-mono text-xs font-bold tracking-wider rounded hover:bg-purple-600/50 transition-colors border border-purple-500/50 flex justify-center items-center gap-2"
                            >
                              <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                                <path d="M8 5v14l11-7z" />
                              </svg>
                              PLAY AT OFFSET
                            </button>
                          </div>
                        </div>
                      )}

                      {!showVideo && (
                        <div className="p-4 text-center">
                          <button
                            onClick={() => setShowVideo(true)}
                            className="px-4 py-2 bg-purple-600/30 text-purple-300 font-mono text-xs font-bold rounded hover:bg-purple-600/50 transition-colors border border-purple-500/50"
                          >
                            Load Video
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Action Buttons */}
                  <div className="flex gap-2 pt-2">
                    <button
                      onClick={handleOpenTrace}
                      className="flex-1 py-3 bg-cyan-950/60 border border-cyan-700/60 rounded-lg
                        font-mono text-xs font-bold tracking-wider text-cyan-400 hover:bg-cyan-900/60 transition-colors"
                    >
                      TRACE PERSON
                    </button>
                    {detectionDetail?.video_id && (
                      <button
                        onClick={() => {
                          const params = new URLSearchParams({
                            video: detectionDetail.video_id,
                            time: targetOffset.toString(),
                            timestamp: detectionDetail?.timestamp || imageTarget.timestamp,
                            camera_id: detectionDetail?.camera_id || imageTarget.camera_id,
                            clothing_class: detectionDetail?.class_name || imageTarget.clothing_class,
                            color: detectionDetail?.category || imageTarget.color,
                            confidence: (detectionDetail?.confidence || imageTarget.confidence)?.toString() || "0",
                            play: "true"
                          });
                          window.open(`/search?${params.toString()}`, '_blank');
                        }}
                        className="flex-1 py-3 bg-purple-950/60 border border-purple-700/60 rounded-lg
                          font-mono text-xs font-bold tracking-wider text-purple-400 hover:bg-purple-900/60 transition-colors"
                      >
                        OPEN IN SEARCH
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Mini Player */}
      {videoPopupOpen && detectionDetail?.video_id && (
        <div
          ref={miniPlayerRef}
          className={`fixed z-[60] bg-slate-900 rounded-lg border border-slate-700 shadow-2xl overflow-hidden transition-all duration-200 ${isDragging ? 'cursor-grabbing' : isResizing ? 'cursor-se-resize' : 'cursor-grab'}`}
          style={{
            left: `${playerPosition.x}px`,
            right: 'auto',
            bottom: `${playerPosition.y}px`,
            top: 'auto',
            width: getPlayerStyle().width,
            height: getPlayerStyle().height,
          }}
        >
          {/* Draggable Header Bar */}
          <div
            className="mini-player-controls flex items-center justify-between px-3 py-2 bg-slate-950/80 border-b border-slate-800 select-none"
            onMouseDown={handleDragStart}
          >
            <div className="flex items-center gap-2">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4 text-slate-500">
                <path d="M4 8h16M4 16h16" />
              </svg>
              <span className="font-mono text-xs text-slate-400">Offset: {targetOffset.toFixed(2)}s</span>
            </div>
            <div className="flex items-center gap-1">
              {/* Size toggle */}
              <button
                onClick={cycleSize}
                className="p-1.5 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
                title="Toggle size"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                  <path d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                </svg>
              </button>
              {/* Minimize toggle */}
              <button
                onClick={toggleMinimize}
                className="p-1.5 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
                title={isMinimized ? "Expand" : "Minimize"}
              >
                {isMinimized ? (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                    <path d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                    <path d="M18 12H6" />
                  </svg>
                )}
              </button>
              {/* Close */}
              <button
                onClick={closeVideoPopup}
                className="p-1.5 rounded text-slate-500 hover:text-red-400 hover:bg-red-950/30 transition-colors"
                title="Close"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Video Player (hidden when minimized) */}
          {!isMinimized && (
            <>
              <div className="relative bg-black flex-1" style={{ height: `calc(100% - 80px)` }}>
                <video
                  ref={popupVideoRef}
                  controls
                  autoPlay
                  className="w-full h-full"
                  src={`/api/video/videos/${detectionDetail.video_id}/stream`}
                  onLoadedMetadata={() => {
                    if (popupVideoRef.current) {
                      popupVideoRef.current.currentTime = targetOffset;
                      popupVideoRef.current.play().catch(() => {});
                    }
                  }}
                />
              </div>

              {/* Controls */}
              <div className="absolute bottom-0 left-0 right-0 px-3 py-2 bg-slate-950/90 border-t border-slate-800 mini-player-controls">
                <div className="flex items-center justify-between gap-2">
                  <button
                    onClick={() => adjustOffset(-1)}
                    className="px-2 py-1 bg-slate-800 text-slate-300 font-mono text-xs font-bold rounded hover:bg-slate-700 transition-colors border border-slate-700"
                  >
                    -1s
                  </button>

                  <div className="flex-1 text-center">
                    <span className="font-mono text-xs text-slate-500 uppercase block">Offset</span>
                    <span className="font-mono text-sm font-bold text-purple-400">{targetOffset.toFixed(2)}s</span>
                  </div>

                  <button
                    onClick={() => adjustOffset(1)}
                    className="px-2 py-1 bg-slate-800 text-slate-300 font-mono text-xs font-bold rounded hover:bg-slate-700 transition-colors border border-slate-700"
                  >
                    +1s
                  </button>
                </div>

                <button
                  onClick={resetOffset}
                  className="w-full mt-2 py-1 bg-slate-800/50 text-slate-400 font-mono text-[10px] font-bold tracking-wider rounded hover:bg-slate-700/50 transition-colors border border-slate-700/50"
                >
                  RESET
                </button>
              </div>
            </>
          )}

          {/* Resize Handle - bottom right corner */}
          {!isMinimized && (
            <div
              className="absolute bottom-0 right-0 w-5 h-5 cursor-se-resize z-10 group"
              onMouseDown={handleResizeStart}
            >
              {/* Resize indicator lines */}
              <svg
                className="absolute bottom-1 right-1 w-3 h-3 text-slate-600 group-hover:text-slate-400 transition-colors"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path d="M22 22L16 16M22 16L16 22" />
                <path d="M22 16L16 10M16 22L10 16" strokeOpacity={0.5} />
              </svg>
              {/* Invisible hit area for easier grabbing */}
              <div className="absolute inset-0" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}