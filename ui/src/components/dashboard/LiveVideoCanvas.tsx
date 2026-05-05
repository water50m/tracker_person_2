"use client";

import { useEffect, useRef, useState } from "react";

import HlsVideoPlayer from "./HlsVideoPlayer";

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
  const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
  const match = url.match(regExp);
  if (match && match[2].length === 11) {
    return `https://www.youtube.com/embed/${match[2]}?autoplay=1&mute=1&controls=0&modestbranding=1`;
  }
  return null;
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

  const containerRef = useRef<HTMLDivElement>(null);
  const streamKeyRef = useRef<number>(Date.now()); // Used to force image reload if needed

  // Fetch cameras
  useEffect(() => {
    const fetchCameras = async () => {
      try {
        const res = await fetch("/api/dashboard/cameras");
        if (res.ok) {
          const data = await res.json();
          const cams: CameraOption[] = data.cameras || [];
          setCameras(cams);

          setSelectedCamera(prevSelected => {
            if (!prevSelected) {
              return cams.length > 0 ? cams[0] : null;
            }
            // Update the selected camera with fresh data from server (e.g. is_processing changed)
            const freshCam = cams.find(c => c.id === prevSelected.id);
            return freshCam || prevSelected;
          });
        }
      } catch (err) {
        console.error("Failed to fetch cameras:", err);
      }
    };
    fetchCameras();
    const t = setInterval(fetchCameras, 30000); // 30s refresh for camera list
    return () => clearInterval(t);
  }, []);

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
    try {
      const res = await fetch(`/api/dashboard/prediction/${selectedCamera.id}/stop`, {
        method: "POST"
      });
      if (res.ok) {
        // Optimistic update
        setSelectedCamera(prev => prev ? { ...prev, is_processing: false } : null);
        setCameras(prev => prev.map(c => c.id === selectedCamera.id ? { ...c, is_processing: false } : c));
        streamKeyRef.current = Date.now();
      }
    } catch (err) {
      console.error("Failed to stop prediction:", err);
    } finally {
      setIsStoppingAI(false);
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
        setSelectedCamera(prev => prev ? { ...prev, is_processing: true } : null);
        setCameras(prev => prev.map(c => c.id === selectedCamera.id ? { ...c, is_processing: true } : c));
        streamKeyRef.current = Date.now();
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
                  <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${cam.is_active ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
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
              </div>
            )}
          </span>
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
              {(() => {
                if (selectedCamera.is_processing) {
                  return (
                    // ── Active AI Stream ──
                    <img
                      key={streamKeyRef.current} // forces reload when camera changes
                      src={`/api/dashboard/mjpeg/${selectedCamera.id}`}
                      alt="Live MJPEG Stream"
                      className="w-full h-full object-contain"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        e.currentTarget.parentElement?.classList.add('stream-error');
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

            {/* Scanning Overlay Effect */}
            <div
              className="absolute inset-0 pointer-events-none opacity-20"
              style={{
                background: "repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.4) 2px,rgba(0,0,0,0.4) 4px)",
              }}
            />

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
              <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${cam.is_active ? "bg-green-500" : "bg-red-600"}`} />
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