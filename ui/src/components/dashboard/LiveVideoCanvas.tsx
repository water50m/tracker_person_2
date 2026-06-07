"use client";

import { useEffect, useRef, useState, useCallback } from "react";

import HlsVideoPlayer from "./HlsVideoPlayer";
import IPCameraPlayer from "./IPCameraPlayer";

// ─── Types ────────────────────────────────────────────────────

interface CameraOption {
  id: string;
  name: string;
  source_url: string;
  is_active: boolean;
  is_processing: boolean;
}

interface DetectionCard {
  id: string;
  track_id: number;
  timestamp: string;
  image_url: string | null;
  category: string;
  class_name: string;
  color_profile: Record<string, number>;
}

// ─── Utilities ────────────────────────────────────────────────

function getYoutubeEmbedUrl(url: string): string | null {
  const trimmed = (url || "").trim();
  if (!trimmed) return null;

  const idMatch =
    trimmed.match(/(?:youtu\.be\/)([A-Za-z0-9_-]{11})/) ||
    trimmed.match(/[?&]v=([A-Za-z0-9_-]{11})/) ||
    trimmed.match(/\/shorts\/([A-Za-z0-9_-]{11})/) ||
    trimmed.match(/\/embed\/([A-Za-z0-9_-]{11})/);

  const videoId = idMatch?.[1];
  if (!videoId) return null;
  return `https://www.youtube.com/embed/${videoId}?autoplay=1&mute=1&controls=0&modestbranding=1`;
}

function isIPCameraUrl(url: string): boolean {
  // Check for common IP camera protocols and patterns
  const ipCameraPatterns = [
    /^rtsp:\/\//i,                    // RTSP protocol
    /^rtmp:\/\//i,                    // RTMP protocol  
    /^http:\/\/.*\/mjpg/,             // MJPEG over HTTP
    /^http:\/\/.*\/mjpeg/,            // MJPEG over HTTP (alternative)
    /^http:\/\/.*\/video/,            // Common video endpoints (including IP Webcam)
    /^http:\/\/.*\/stream/,           // Common stream endpoints
    /^http:\/\/.*\/live/,             // Common live endpoints
    /^http:\/\/.*\/cam/,              // Common camera endpoints
    /:\d{4,5}/,                       // Port numbers (common for IP cameras)
    /\/cgi-bin\/video/,               // Common CGI video endpoints
    /\/onvif/,                        // ONVIF protocol
    // IP Webcam app specific patterns
    /:8080\/video/,                   // IP Webcam video stream
    /:8080\/shot\.jpg/,               // IP Webcam single image
    /ipwebcam/i,                      // IP Webcam app identifier
  ];
  
  return ipCameraPatterns.some(pattern => pattern.test(url));
}

// ─── Component ────────────────────────────────────────────────

export default function LiveVideoCanvas() {
  const [cameras, setCameras] = useState<CameraOption[]>([]);
  const [selectedCamera, setSelectedCamera] = useState<CameraOption | null>(null);
  const [showCameraList, setShowCameraList] = useState(false);
  const [detections, setDetections] = useState<DetectionCard[]>([]);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isStartingAI, setIsStartingAI] = useState(false);
  const [isStoppingAI, setIsStoppingAI] = useState(false);
  const [frameTiming, setFrameTiming] = useState<string>("");
  const [showAISettings, setShowAISettings] = useState(false);
  // camera_id → reachability status
  const [health, setHealth] = useState<Record<string, { reachable: boolean; latency_ms: number | null; checked_at: string; error: string | null }>>({});
  const [isRechecking, setIsRechecking] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const streamKeyRef = useRef<number>(Date.now()); // Used to force image reload if needed
  const frameReceiveTimeRef = useRef<number>(Date.now()); // Track when frames are received
  
  // Stream error counter and connection management
  const [streamErrorCounts, setStreamErrorCounts] = useState<Record<string, number>>({});

  function setStreamErrorCount(cameraId: string, count: number) {
    setStreamErrorCounts(prev => ({
      ...prev,
      [cameraId]: count
    }));
  }

  function getStreamErrorCount(cameraId: string): number {
    return streamErrorCounts[cameraId] || 0;
  }

  // Fetch cameras — syncs is_processing state from backend
  const fetchCameras = useCallback(async () => {
    try {
      const res = await fetch("/api/dashboard/cameras");
      if (!res.ok) return;
      const data = await res.json();
      const cams: CameraOption[] = data.cameras || [];
      setCameras(cams);
      setSelectedCamera(prevSelected => {
        if (!prevSelected) {
          const processingCam = cams.find(c => c.is_processing);
          return processingCam ?? (cams.length > 0 ? cams[0] : null);
        }
        const freshCam = cams.find(c => c.id === prevSelected.id);
        return freshCam ?? prevSelected;
      });
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    fetchCameras();
    // 4s poll — fast enough to detect external stop/start, low enough not to spam
    const t = setInterval(fetchCameras, 4000);
    return () => clearInterval(t);
  }, [fetchCameras]);

  // Fetch camera reachability (backend checks every 10 min)
  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch("/api/dashboard/camera-health", { cache: "no-store" });
      if (res.ok) { const data = await res.json(); setHealth(data.health || {}); }
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    fetchHealth();
    const t = setInterval(fetchHealth, 60000);
    return () => clearInterval(t);
  }, [fetchHealth]);

  // Force an immediate reachability recheck for the selected camera
  const recheckHealth = useCallback(async () => {
    if (!selectedCamera) return;
    setIsRechecking(true);
    try {
      const res = await fetch(`/api/dashboard/camera-health/${encodeURIComponent(selectedCamera.id)}/recheck`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        if (data.status) setHealth(prev => ({ ...prev, [selectedCamera.id]: data.status }));
      }
    } catch { /* silent */ } finally {
      setIsRechecking(false);
    }
  }, [selectedCamera]);

  // Fetch latest detections for the selected camera
  useEffect(() => {
    if (!selectedCamera?.is_processing) {
      setDetections([]);
      return;
    }

    const fetchDetections = async () => {
      try {
        const res = await fetch(`/api/dashboard/latest-detections/${selectedCamera.id}?limit=5`);
        if (res.ok) {
          const data = await res.json();
          setDetections(data.detections || []);
        }
      } catch (err) {
        console.error("Failed to fetch detections:", err);
      }
    };

    fetchDetections();
    const t = setInterval(fetchDetections, 4000);
    return () => clearInterval(t);
  }, [selectedCamera]);

  // Handle camera selection
  const handleSelectCamera = (cam: CameraOption) => {
    setSelectedCamera(cam);
    setShowCameraList(false);
    streamKeyRef.current = Date.now(); // Force stream img refresh
  };

  // Handle Stop Prediction
  const stopPrediction = async () => {
    if (!selectedCamera || !selectedCamera.is_processing) return;

    setIsStoppingAI(true);
    const stoppingCameraId = selectedCamera.id;
    try {
      const res = await fetch(`/api/dashboard/prediction/${stoppingCameraId}/stop`, { method: "POST" });
      if (!res.ok) console.warn("Stop returned non-ok:", res.status);
    } catch (err) {
      console.error("Failed to stop prediction:", err);
    } finally {
      // Always transition UI to stopped — even on network error or 404 (pipeline already stopped)
      setSelectedCamera(prev => prev ? { ...prev, is_processing: false } : null);
      setCameras(prev => prev.map(c => c.id === stoppingCameraId ? { ...c, is_processing: false } : c));
      streamKeyRef.current = Date.now();
      setIsStoppingAI(false);
      setTimeout(fetchCameras, 500);
    }
  };

  // Handle Start Prediction
  const startPrediction = async (resume: boolean = false) => {
    if (!selectedCamera || selectedCamera.is_processing) return;

    setIsStartingAI(true);
    try {
      const res = await fetch(`/api/dashboard/prediction/${selectedCamera.id}/start?resume=${resume}`, {
        method: "POST"
      });
      if (res.ok) {
        // Optimistic update so STOP button appears immediately
        setSelectedCamera(prev => prev ? { ...prev, is_processing: true } : null);
        setCameras(prev => prev.map(c => c.id === selectedCamera.id ? { ...c, is_processing: true } : c));
        streamKeyRef.current = Date.now();
        // Confirm with backend after stream has had time to start
        setTimeout(fetchCameras, 1500);
      }
    } catch (err) {
      console.error("Failed to start prediction:", err);
    } finally {
      setIsStartingAI(false);
    }
  };

  if (!selectedCamera) {
    return (
      <div className="hud-panel flex flex-col items-center justify-center min-h-0 text-slate-500 font-mono text-xs">
        Loading Cameras...
      </div>
    );
  }

  const isOnline = selectedCamera.is_active;

  return (
    <div className="hud-panel flex flex-col min-h-0 overflow-hidden relative">
      {/* ── Top bar ── */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-cyan-900/30 flex-shrink-0 bg-slate-950/80 z-20">
        {/* Camera selector */}
        <div className="relative">
          <button
            onClick={() => setShowCameraList((s) => !s)}
            className="flex items-center gap-2 group"
          >
            <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isOnline ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
            <span className="font-orbitron text-[10px] text-cyan-400 tracking-widest group-hover:text-cyan-300 transition-colors">
              {selectedCamera.name.toUpperCase()}
            </span>
            <span className="font-mono text-[8px] text-slate-600 ml-1">
              {selectedCamera.id}
            </span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3 text-slate-600">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>

          {/* Dropdown */}
          {showCameraList && (
            <div className="absolute top-full left-0 mt-1 z-50 w-64 glass border border-cyan-900/50 rounded-sm shadow-xl max-h-60 overflow-y-auto">
              {cameras.map((cam) => (
                <button
                  key={cam.id}
                  onClick={() => handleSelectCamera(cam)}
                  className="w-full flex items-center gap-3 px-3 py-2 hover:bg-cyan-950/40 transition-colors text-left border-b border-cyan-900/20 last:border-0"
                >
                  {(() => {
                    const h = health[cam.id];
                    const dotClass = !h ? "bg-slate-600" : h.reachable ? "bg-green-500 animate-pulse" : "bg-red-500";
                    const title = !h ? "Status unknown" : h.reachable ? `Active${h.latency_ms != null ? ` · ${Math.round(h.latency_ms)}ms` : ""}` : `Can't connect: ${h.error || "no connection"}`;
                    return <div title={title} className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotClass}`} />;
                  })()}
                  <div className="flex-1">
                    <div className="font-mono text-[10px] text-slate-300">{cam.name}</div>
                    <div className="font-mono text-[8px] text-slate-600">{cam.id}</div>
                  </div>
                  {cam.is_processing && (
                    <span className="font-mono text-[8px] px-1.5 py-0.5 rounded bg-cyan-900/50 text-cyan-400 border border-cyan-800">
                      AI ACTIVE
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right Controls */}
        <div className="flex items-center gap-4">
          <span className="font-mono text-[9px] text-slate-600 flex items-center gap-1.5">
            AI:
            {selectedCamera.is_processing ? (
              <div className="flex items-center gap-2">
                <span className={"text-cyan-400"}>
                  PROCESSING
                </span>
                <button
                  onClick={stopPrediction}
                  disabled={isStoppingAI}
                  className="px-1.5 py-0.5 hover:bg-red-900/50 rounded transition-colors text-red-500 hover:text-red-400 border border-transparent hover:border-red-800 disabled:opacity-50"
                  title={"Stop AI and return to native stream"}
                >
                  {isStoppingAI ? (
                    <div className="w-3 h-3 border-2 border-red-500/30 border-t-red-400 rounded-full animate-spin" />
                  ) : (
                    <svg viewBox="0 0 24 24" fill="currentColor" className="w-3 h-3">
                      <rect x="6" y="6" width="12" height="12" rx="1" />
                    </svg>
                  )}
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => startPrediction(false)}
                  disabled={isStartingAI}
                  className="flex items-center gap-1.5 px-3 py-1 bg-cyan-900/60 hover:bg-cyan-800 text-cyan-50 border border-cyan-700/60 hover:border-cyan-500 rounded transition-all disabled:opacity-50 shadow-[0_0_10px_rgba(6,182,212,0.2)] font-bold tracking-wider"
                  title="Start AI from current frame (Fresh Session)"
                >
                  {isStartingAI ? (
                    <div className="w-3 h-3 border-2 border-cyan-100/30 border-t-cyan-50 rounded-full animate-spin" />
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3 h-3">
                      <path d="M5 3l14 9-14 9V3z" />
                    </svg>
                  )}
                  <span>START NEW</span>
                </button>
                <button
                  onClick={() => startPrediction(true)}
                  disabled={isStartingAI}
                  className="flex items-center gap-1.5 px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-500 rounded transition-all disabled:opacity-50"
                  title="Resume AI from last paused frame (If available)"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3">
                    <path d="M12 2v20M17 5v14M7 5v14" />
                  </svg>
                  <span>RESUME</span>
                </button>
                {/* AI Settings gear button */}
                <button
                  onClick={() => setShowAISettings(true)}
                  className="p-1 text-slate-500 hover:text-cyan-400 border border-transparent hover:border-slate-700 rounded transition-all"
                  title="AI Processing Settings"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-4 h-4">
                    <path d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
                    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
                  </svg>
                </button>
              </div>
            )}
          </span>
          {/* AI Settings Modal — rendered outside toolbar flow */}
          {showAISettings && (
            <AISettingsModal onClose={() => setShowAISettings(false)} />
          )}
          <button
            onClick={() => setIsFullscreen((s) => !s)}
            className="p-1 hover:text-cyan-400 text-slate-600 transition-colors"
            title="Fullscreen"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-4 h-4">
              {isFullscreen
                ? <path d="M8 3v3a2 2 0 01-2 2H3m18 0h-3a2 2 0 01-2-2V3m0 18v-3a2 2 0 012-2h3M3 16h3a2 2 0 012 2v3" />
                : <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
              }
            </svg>
          </button>
        </div>
      </div>

      {/* ── Video area ── */}
      <div
        ref={containerRef}
        className="relative flex-1 bg-black overflow-hidden flex items-center justify-center min-h-0"
        style={{ minHeight: 0 }}
      >
        {!isOnline ? (
          /* Offline state */
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-950">
            <div className="w-12 h-12 border border-red-900/60 rounded-full flex items-center justify-center bg-red-950/20">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-6 h-6 text-red-500">
                <path d="M18.364 5.636a9 9 0 11-12.728 0M12 3v9" />
              </svg>
            </div>
            <p className="font-mono text-[10px] text-red-500 tracking-widest">CAMERA OFFLINE</p>
            <p className="font-mono text-[9px] text-slate-600">{selectedCamera.id}</p>
          </div>
        ) : (
          <>
            {/* Live MJPEG Stream or Native Player */}
            <div className="w-full h-full relative">
              {/* Stopping overlay — backend waits for the pipeline to fully finish */}
              {isStoppingAI && (
                <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 bg-slate-950">
                  <div className="w-16 h-16 border-4 border-red-500/20 border-t-red-400 rounded-full animate-spin" />
                  <p className="font-mono text-xs text-red-300 tracking-widest animate-pulse">STOPPING AI…</p>
                  <p className="font-mono text-[10px] text-slate-500">finalizing results</p>
                </div>
              )}

              {/* Not-ready banner — camera failed the latest reachability check */}
              {health[selectedCamera.id]?.reachable === false && !isStoppingAI && (
                <div className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between gap-3 px-4 py-2 bg-red-950/85 backdrop-blur-sm border-b border-red-700/60">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0 animate-pulse" />
                    <div className="min-w-0">
                      <p className="font-mono text-[11px] text-red-300 tracking-widest">CAMERA NOT READY</p>
                      <p className="font-mono text-[9px] text-red-400/70 truncate">
                        {health[selectedCamera.id]?.error || "ติดต่อกล้องไม่ได้ — ตรวจสอบการเชื่อมต่อ"}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={recheckHealth}
                    disabled={isRechecking}
                    title="Recheck reachability now"
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-sm border border-red-600/60 text-red-300 hover:bg-red-900/40 hover:text-red-200 transition-colors disabled:opacity-50 flex-shrink-0"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={`w-3 h-3 ${isRechecking ? "animate-spin" : ""}`}>
                      <path d="M23 4v6h-6M1 20v-6h6" />
                      <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
                    </svg>
                    <span className="font-mono text-[9px] tracking-wider">RECONNECT</span>
                  </button>
                </div>
              )}
              {(() => {
                if (selectedCamera.is_processing) {
                  return (
                    // ── Active AI Stream ──
                    <img
                      key={streamKeyRef.current} // forces reload when camera changes
                      src={`/api/dashboard/mjpeg/${selectedCamera.id}`}
                      alt="Live MJPEG Stream"
                      className="w-full h-full object-contain"
                      onLoad={() => {
                        const receiveTime = Date.now();
                        const timeSinceLastFrame = receiveTime - frameReceiveTimeRef.current;
                        frameReceiveTimeRef.current = receiveTime;
                        
                        const timingText = `Frame received: ${timeSinceLastFrame}ms`;
                        setFrameTiming(timingText);
                        console.log(`[LiveVideoCanvas] 📱 RECEIVED MJPEG frame for camera ${selectedCamera.id}, time since last: ${timeSinceLastFrame}ms`);
                        
                        // Reset connection error counter on successful load
                        setStreamErrorCount(selectedCamera.id, 0);
                      }}
                      onError={(e) => {
                        console.error(`[LiveVideoCanvas] ❌ MJPEG stream error for camera ${selectedCamera.id}`, e);
                        
                        // Try to reload after network error
                        const errorDetails = (e as any).message || (e as any).toString() || '';
                        const errorCount = getStreamErrorCount(selectedCamera.id) + 1;
                        setStreamErrorCount(selectedCamera.id, errorCount);
                        
                        // Check if camera is still processing
                        if (selectedCamera.is_processing) {
                          console.log(`[LiveVideoCanvas] 🔄 Stream error #${errorCount} for camera ${selectedCamera.id}, camera still processing, reloading in ${Math.min(1000 * errorCount, 5000)}ms...`);
                          
                          // Force reload by changing src with exponential backoff
                          const img = e.currentTarget;
                          const currentSrc = img.src;
                          img.src = '';
                          
                          // Exponential backoff: 1s, 2s, 3s, 4s, 5s max
                          const retryDelay = Math.min(1000 * errorCount, 5000);
                          setTimeout(() => {
                            // Add timestamp and error count to prevent caching
                            const newSrc = currentSrc.split('?')[0] + `?t=${Date.now()}&retry=${errorCount}`;
                            img.src = newSrc;
                          }, retryDelay);
                          
                          // If too many errors, stop trying and show error
                          if (errorCount >= 10) {
                            console.error(`[LiveVideoCanvas] ❌ Too many connection errors (${errorCount}), stopping reload attempts for camera ${selectedCamera.id}`);
                            e.currentTarget.style.display = 'none';
                            e.currentTarget.parentElement?.classList.add('stream-error');
                          }
                        } else {
                          console.log(`[LiveVideoCanvas] Camera ${selectedCamera.id} is no longer processing, stopping reload attempts`);
                          e.currentTarget.style.display = 'none';
                          e.currentTarget.parentElement?.classList.add('stream-error');
                        }
                      }}
                    />
                  );
                }

                // ── Inactive Local/Native Video ──
                const ytEmbed = getYoutubeEmbedUrl(selectedCamera.source_url);
                if (ytEmbed) {
                  return (
                    <iframe
                      src={ytEmbed}
                      className="w-full h-full object-cover pointer-events-none"
                      allow="autoplay; encrypted-media"
                      title="YouTube stream"
                    />
                  );
                }

                // Check for IP camera URLs — always relay through backend to avoid CORS
                if (isIPCameraUrl(selectedCamera.source_url)) {
                  return (
                    <img
                      key={`raw-${selectedCamera.id}-${streamKeyRef.current}`}
                      src={`/api/dashboard/mjpeg/${selectedCamera.id}`}
                      alt="IP camera relay stream"
                      className="w-full h-full object-contain"
                      onError={(e) => {
                        const img = e.currentTarget;
                        const currentSrc = img.src.split('?')[0];
                        if (!currentSrc) return;
                        img.src = '';
                        setTimeout(() => {
                          img.src = `${currentSrc}?t=${Date.now()}`;
                        }, 1500);
                      }}
                    />
                  );
                }

                // Other source types fallback (.m3u8 or .mp4)
                if (selectedCamera.source_url.includes('.m3u8') || selectedCamera.source_url.includes('.mp4')) {
                  return <HlsVideoPlayer src={selectedCamera.source_url} />;
                }

                return (
                  <div className="flex items-center justify-center w-full h-full bg-slate-900 flex-col gap-2">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-8 h-8 text-slate-700">
                      <path d="M15 10l4.553-2.277A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    <p className="font-mono text-xs text-slate-500 tracking-widest">RAW RTSP PREVIEW UNAVAILABLE</p>
                    <p className="font-mono text-[9px] text-slate-600">Click START AI to begin processing & view stream</p>
                  </div>
                );
              })()}

              <div className="error-overlay hidden absolute inset-0 flex-col items-center justify-center gap-3 bg-slate-950 text-slate-500">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-8 h-8 text-slate-700">
                  <path d="M15 10l4.553-2.277A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                <p className="font-mono text-xs">STREAM UNAVAILABLE</p>
              </div>
            </div>


            {/* Detection Cards Overlay (Right Side) */}
            {selectedCamera.is_processing && detections.length > 0 && (
              <div className="absolute right-4 top-4 bottom-4 w-48 flex flex-col gap-2 overflow-y-auto pointer-events-none mask-fade-y">
                {detections.map((det) => (
                  <div key={det.id} className="bg-slate-950/80 border border-cyan-900/50 rounded-sm p-2 flex gap-2 backdrop-blur-sm shadow-xl pointer-events-auto transition-all hover:border-cyan-500/50">
                    {det.image_url ? (
                      <img src={det.image_url} alt="Crop" className="w-10 h-14 object-cover rounded-sm border border-slate-800" />
                    ) : (
                      <div className="w-10 h-14 bg-slate-900 flex items-center justify-center border border-slate-800 rounded-sm">
                        <span className="text-[8px] text-slate-600">NO IMG</span>
                      </div>
                    )}
                    <div className="flex-1 min-w-0 flex flex-col justify-center">
                      <div className="font-orbitron text-[9px] text-cyan-400 truncate">{det.class_name.toUpperCase()}</div>
                      <div className="font-mono text-[8px] text-slate-400 mt-0.5">{det.category}</div>
                      <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                        {Object.entries(det.color_profile).slice(0, 3).map(([color, pct], i) => (
                          <div
                            key={i}
                            className="w-2.5 h-2.5 rounded-full border border-slate-700"
                            style={{ backgroundColor: color, opacity: pct }}
                            title={`${color} ${(pct * 100).toFixed(0)}%`}
                          />
                        ))}
                      </div>
                      <div className="font-mono text-[7px] text-slate-600 mt-1 truncate">
                        ID: {det.track_id}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Corner HUD decorations */}
            <div className="absolute top-3 left-3 pointer-events-none">
              <div className="font-mono text-[9px] text-cyan-400 tracking-wider font-bold drop-shadow-md">
                {selectedCamera.id}
              </div>
              <div className="font-mono text-[8px] text-white/70 tracking-widest mt-0.5 drop-shadow-md">
                LIVE STREAM
              </div>
            </div>

            {/* REC indicator if AI is processing */}
            {selectedCamera.is_processing && (
              <div className={`absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-2 py-0.5 border rounded pointer-events-none transition-colors
                bg-red-950/50 border-red-900/50`
              }>
                <div className={`w-1.5 h-1.5 rounded-full animate-pulse bg-red-500 box-shadow-red`} />
                <span className={`font-mono text-[8px] tracking-widest font-bold text-red-400`}>
                  ANALYSIS ACTIVE
                </span>
              </div>
            )}

            {/* Bottom timestamp */}
            <div className="absolute bottom-3 left-3 bg-black/50 px-1.5 py-0.5 rounded font-mono text-[9px] text-slate-300 pointer-events-none border border-slate-800/50">
              <LiveTimestamp />
            </div>

            {/* Frame timing display */}
            {selectedCamera.is_processing && frameTiming && (
              <div className="absolute top-3 right-3 bg-black/70 px-2 py-1 rounded font-mono text-[10px] text-cyan-400 pointer-events-none border border-cyan-800/50">
                {frameTiming}
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Bottom bar: camera strip ── */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-cyan-900/30 flex-shrink-0 overflow-x-auto bg-slate-950/80 z-20">
        {cameras.map((cam) => (
          <button
            key={cam.id}
            onClick={() => handleSelectCamera(cam)}
            className={`
              flex-shrink-0 flex flex-col px-3 py-1.5 rounded-sm border transition-all min-w-[100px]
              ${selectedCamera?.id === cam.id
                ? "border-cyan-500/60 bg-cyan-950/50 shadow-[0_0_10px_rgba(6,182,212,0.1)]"
                : "border-slate-800/80 bg-slate-900/30 hover:border-slate-700 hover:bg-slate-900/60"
              }
            `}
          >
            <div className="flex items-center gap-1.5 mb-1">
              {(() => {
                const h = health[cam.id];
                const dotClass = !h
                  ? "bg-slate-600"                       // not checked yet
                  : h.reachable
                    ? "bg-green-500 animate-pulse"        // reachable
                    : "bg-red-500";                       // unreachable
                const title = !h
                  ? "Reachability unknown"
                  : h.reachable
                    ? `Active${h.latency_ms != null ? ` · ${Math.round(h.latency_ms)}ms` : ""}`
                    : `Can't connect: ${h.error || "no connection"}`;
                return <div title={title} className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotClass}`} />;
              })()}
              <span className={`font-mono text-[9px] tracking-wider font-bold ${selectedCamera?.id === cam.id ? "text-cyan-400" : "text-slate-400"}`}>
                ID: {cam.id}
              </span>
            </div>
            <div className="flex items-center gap-2 justify-between w-full">
              <span className="font-orbitron text-[8px] text-slate-500 truncate max-w-[60px]">{cam.name}</span>
              {cam.is_processing && (
                <span className="flex items-center gap-1">
                  <span className={`w-1 h-1 rounded-full animate-pulse bg-cyan-400`} />
                  <span className={`font-mono text-[7px] text-cyan-600`}>AI</span>
                </span>
              )}
            </div>
          </button>
        ))}
        {cameras.length === 0 && (
          <div className="font-mono text-[9px] text-slate-600 w-full text-center py-2">NO CAMERAS CONFIGURED</div>
        )}
      </div>

      <style dangerouslySetInnerHTML={{
        __html: `
         .stream-error + .error-overlay { display: flex; }
         .box-shadow-red { box-shadow: 0 0 8px rgba(239, 68, 68, 0.6); }
         .box-shadow-yellow { box-shadow: 0 0 8px rgba(234, 179, 8, 0.6); }
         .mask-fade-y { mask-image: linear-gradient(to bottom, transparent, black 5%, black 95%, transparent); }
      `}} />
    </div>
  );
}

function LiveTimestamp() {
  const [ts, setTs] = useState("");
  useEffect(() => {
    const update = () => setTs(new Date().toLocaleTimeString("en-GB", { hour12: false }));
    update();
    const t = setInterval(update, 1000);
    return () => clearInterval(t);
  }, []);
  return <span>{ts}</span>;
}

// ─── AI Settings Modal ────────────────────────────────────────
const RESOLUTION_OPTIONS = [
  { label: "480p",  height: 480,  desc: "เบา / bandwidth ต่ำ" },
  { label: "720p",  height: 720,  desc: "สมดุล (แนะนำ)" },
  { label: "1080p", height: 1080, desc: "คมชัด / default" },
  { label: "ต้นฉบับ", height: 0, desc: "ส่งตามขนาดจริงของกล้อง" },
] as const;

function AISettingsModal({ onClose }: { onClose: () => void }) {
  const [aiFrameSkip, setAiFrameSkip] = useState<number>(5);
  const [outputHeight, setOutputHeight] = useState<number>(1080);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const backendUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace("://localhost:", "://127.0.0.1:");

  useEffect(() => {
    fetch(`${backendUrl}/api/settings`, { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        const skip = d?.config?.stream?.ai_frame_skip;
        if (typeof skip === "number") setAiFrameSkip(skip);
        const oh = d?.config?.stream?.output_height;
        if (typeof oh === "number") setOutputHeight(oh);
      })
      .catch(() => {});
  }, [backendUrl]);

  const handleSave = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const res = await fetch(`${backendUrl}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stream: { ai_frame_skip: aiFrameSkip, output_height: outputHeight } }),
      });
      setMsg(res.ok ? "✓ SAVED" : "✗ FAILED");
    } catch {
      setMsg("✗ ERROR");
    } finally {
      setSaving(false);
      setTimeout(() => setMsg(null), 2000);
    }
  };

  const estFps = Math.round(30 / aiFrameSkip * 10) / 10;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-slate-950 border border-cyan-900/60 rounded-sm shadow-2xl w-80 p-5 flex flex-col gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-4 h-4 text-cyan-400">
              <path d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
              <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
            </svg>
            <span className="font-mono text-xs font-bold text-cyan-400 tracking-widest">AI SETTINGS</span>
          </div>
          <button onClick={onClose} className="text-slate-600 hover:text-slate-300 transition-colors">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* AI Frame Skip Slider */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono text-[10px] text-slate-400 tracking-widest uppercase">AI Frame Skip</span>
            <span className="font-mono text-lg font-bold text-cyan-400">N = {aiFrameSkip}</span>
          </div>
          <input
            type="range" min={1} max={30} step={1} value={aiFrameSkip}
            onChange={(e) => setAiFrameSkip(parseInt(e.target.value))}
            className="w-full h-1.5 appearance-none rounded-full bg-slate-800 outline-none cursor-pointer
              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
              [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-cyan-400
              [&::-webkit-slider-thumb]:shadow-[0_0_8px_rgba(34,211,238,0.7)] [&::-webkit-slider-thumb]:cursor-pointer"
          />
          <div className="flex justify-between mt-1">
            <span className="font-mono text-[9px] text-slate-600">N=1 (ทุก frame)</span>
            <span className="font-mono text-[9px] text-slate-600">N=30</span>
          </div>
        </div>

        {/* Output Resolution */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono text-[10px] text-slate-400 tracking-widest uppercase">Output Resolution</span>
            <span className="font-mono text-lg font-bold text-cyan-400">
              {RESOLUTION_OPTIONS.find(r => r.height === outputHeight)?.label ?? `${outputHeight}p`}
            </span>
          </div>
          <div className="grid grid-cols-4 gap-1.5">
            {RESOLUTION_OPTIONS.map((opt) => (
              <button
                key={opt.height}
                onClick={() => setOutputHeight(opt.height)}
                className={`flex flex-col items-center gap-0.5 py-2 px-1 rounded-sm border transition-all
                  ${outputHeight === opt.height
                    ? "border-cyan-500/70 bg-cyan-950/50 text-cyan-300"
                    : "border-slate-700 bg-slate-900/40 text-slate-400 hover:border-slate-600 hover:text-slate-300"
                  }`}
              >
                <span className="font-mono text-[11px] font-bold">{opt.label}</span>
                <span className="font-mono text-[8px] text-slate-500 leading-tight text-center">{opt.desc}</span>
              </button>
            ))}
          </div>
          <p className="font-mono text-[9px] text-slate-600 mt-1.5">
            {outputHeight === 0
              ? "ส่งขนาดเต็มของกล้อง — ใช้ bandwidth สูง"
              : `ลด output เป็น ${outputHeight}p — ไม่ upscale ถ้ากล้อง < ${outputHeight}p`}
          </p>
        </div>

        {/* Info */}
        <div className="border border-slate-800 bg-slate-900/40 rounded-sm p-3 flex justify-between">
          <div className="text-center">
            <p className="font-mono text-[9px] text-slate-600 mb-1">ประมวลผลจริง</p>
            <p className="font-mono text-sm font-bold text-cyan-400">~{estFps} fps</p>
          </div>
          <div className="text-center">
            <p className="font-mono text-[9px] text-slate-600 mb-1">Skip ต่อรอบ</p>
            <p className="font-mono text-sm font-bold text-slate-300">{aiFrameSkip - 1} frame</p>
          </div>
          <div className="text-center">
            <p className="font-mono text-[9px] text-slate-600 mb-1">GPU load</p>
            <p className={`font-mono text-sm font-bold ${aiFrameSkip <= 3 ? "text-red-400" : aiFrameSkip <= 7 ? "text-amber-400" : "text-green-400"}`}>
              {aiFrameSkip <= 3 ? "HIGH" : aiFrameSkip <= 7 ? "MED" : "LOW"}
            </p>
          </div>
        </div>

        <p className="font-mono text-[9px] text-slate-600 leading-relaxed">
          มีผลเมื่อกด START NEW ครั้งถัดไป — stream ที่กำลังรันอยู่ไม่ได้รับผลกระทบ
        </p>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {msg && <span className={`font-mono text-xs flex-1 ${msg.startsWith("✓") ? "text-green-400" : "text-red-400"}`}>{msg}</span>}
          <button onClick={onClose} className="flex-1 font-mono text-xs px-3 py-2 border border-slate-700 text-slate-400 hover:text-slate-200 rounded-sm transition-all">
            CANCEL
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex-1 font-mono text-xs font-bold px-3 py-2 border border-cyan-600/60 bg-cyan-950/30 text-cyan-400 hover:bg-cyan-900/40 rounded-sm transition-all disabled:opacity-50"
          >
            {saving ? "SAVING…" : "SAVE"}
          </button>
        </div>
      </div>
    </div>
  );
}
