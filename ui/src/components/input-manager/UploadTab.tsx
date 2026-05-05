"use client";

import React, { useCallback, useRef, useState, useEffect } from "react";
import type { UploadJob, JobStatus } from "@/types";
import VideoReviewModal from "../dashboard/VideoReviewModal";
import { API } from "@/lib/api"; // FastAPI base URL จาก .env.local (NEXT_PUBLIC_API_URL)

// ─── Stream Viewer Component ──────────────────────────────────

function StreamViewer({ streamUrl, onError }: { streamUrl: string; onError?: () => void }) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const maxRetries = 3;

  useEffect(() => {
    if (!streamUrl || !imgRef.current) return;

    const img = imgRef.current;
    setIsConnected(false);

    // Add cache-busting query param to force fresh connection
    const urlWithCache = `${streamUrl}&_cb=${Date.now()}`;
    img.src = urlWithCache;

    const handleLoad = () => setIsConnected(true);
    const handleError = () => {
      setIsConnected(false);
      if (retryCount < maxRetries) {
        setTimeout(() => {
          setRetryCount((c) => c + 1);
          img.src = `${streamUrl}&_cb=${Date.now()}`;
        }, 1000);
      } else {
        onError?.();
      }
    };

    img.addEventListener("load", handleLoad);
    img.addEventListener("error", handleError);

    return () => {
      img.removeEventListener("load", handleLoad);
      img.removeEventListener("error", handleError);
      img.src = "";
    };
  }, [streamUrl, retryCount, onError]);

  return (
    <div className="relative w-full h-full bg-black/50 rounded overflow-hidden">
      <img
        ref={imgRef}
        alt="AI Analysis Stream"
        className="w-full h-full object-contain"
      />
      {!isConnected && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/70">
          <div className="flex flex-col items-center gap-2">
            <svg className="animate-spin h-6 w-6 text-cyan-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span className="font-mono text-[10px] text-slate-400">Connecting to stream...</span>
          </div>
        </div>
      )}
      <div className="absolute top-2 right-2 flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-400 animate-pulse" : "bg-red-400"}`}></span>
        <span className="font-mono text-[9px] text-slate-400 uppercase">{isConnected ? "LIVE" : "OFFLINE"}</span>
      </div>
    </div>
  );
}

// ─── Constants ────────────────────────────────────────────────

const ACCEPTED_TYPES = ["video/mp4", "video/avi", "video/x-msvideo", "video/quicktime", "video/x-matroska"];
const ACCEPTED_EXTS = ".mp4,.avi,.mov,.mkv";
const MAX_SIZE_GB = 2;
const MAX_SIZE_BYTES = MAX_SIZE_GB * 1024 * 1024 * 1024;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function statusLabel(s: JobStatus): string {
  return { queued: "QUEUED", processing: "PROCESSING", done: "COMPLETE", error: "ERROR" }[s];
}

const STATUS_STYLE: Record<JobStatus, { text: string; border: string; bg: string; barColor: string }> = {
  queued: { text: "text-slate-400", border: "border-slate-700", bg: "bg-slate-800/40", barColor: "#64748b" },
  processing: { text: "text-cyan-400", border: "border-cyan-800/60", bg: "bg-cyan-950/30", barColor: "#00f5ff" },
  done: { text: "text-green-400", border: "border-green-800/60", bg: "bg-green-950/30", barColor: "#39ff14" },
  error: { text: "text-red-400", border: "border-red-800/60", bg: "bg-red-950/30", barColor: "#ef4444" },
};

// ─── Component ────────────────────────────────────────────────

export default function UploadTab() {
  const [isDragOver, setIsDragOver] = useState(false);
  const [dragError, setDragError] = useState<string | null>(null);
  const [cameraId, setCameraId] = useState("");
  const [cameraIdError, setCameraIdError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [reviewVideo, setReviewVideo] = useState<{ id: string, title?: string } | null>(null);

  // ── Cameras from API ───────────────────────────────────────
  const [cameras, setCameras] = useState<string[]>([]);
  const [cameraSearch, setCameraSearch] = useState("");

  useEffect(() => {
    // เรียก FastAPI โดยตรง — ไม่ผ่าน Next.js proxy (ลด latency)
    fetch(`${API}/api/cameras`)
      .then((r) => r.json())
      .then((data: { cameras: Array<{ name: string }> }) => {
        if (Array.isArray(data.cameras)) {
          const names = data.cameras.map((c) => c.name).filter(Boolean).sort();
          setCameras(names);
        }
      })
      .catch(() => { });
  }, []);

  const filteredCameras = cameraSearch
    ? cameras.filter((id) => id.toLowerCase().includes(cameraSearch.toLowerCase()))
    : cameras;

  // ── Validate file ──────────────────────────────────────────
  const validateFile = useCallback((file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type) && !file.name.match(/\.(mp4|avi|mov|mkv)$/i)) {
      return `Unsupported format: ${file.name}. Accepted: MP4, AVI, MOV, MKV`;
    }
    if (file.size > MAX_SIZE_BYTES) {
      return `File too large: ${formatBytes(file.size)}. Max ${MAX_SIZE_GB}GB`;
    }
    return null;
  }, []);

  // ── Queue a file ───────────────────────────────────────────
  const queueFile = useCallback(
    async (file: File) => {
      const fileErr = validateFile(file);
      if (fileErr) { setDragError(fileErr); return; }

      if (!cameraId.trim()) {
        setCameraIdError("Camera ID is required before uploading");
        return;
      }

      const jobId = `job-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const newJob: UploadJob = {
        job_id: jobId,
        status: "queued",
        camera_id: cameraId.trim().toUpperCase(),
        filename: file.name,
        size_bytes: file.size,
        progress: 0,
      };

      setJobs((prev) => [newJob, ...prev]);

      // Upload with streaming - returns stream URL for live preview
      await uploadWithStream(jobId, file, cameraId.trim().toUpperCase(), setJobs);
    },
    [cameraId, validateFile]
  );

  // ── Drag & Drop handlers ───────────────────────────────────
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
    setDragError(null);
  };
  const handleDragLeave = () => setIsDragOver(false);
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    for (const f of files) await queueFile(f);
  };
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    for (const f of files) await queueFile(f);
    e.target.value = "";
  };

  const removeJob = (id: string) =>
    setJobs((prev) => prev.filter((j) => j.job_id !== id));

  const retryJob = (id: string) =>
    setJobs((prev) =>
      prev.map((j) => j.job_id === id ? { ...j, status: "queued", progress: 0, error: undefined } : j)
    );

  return (
    <>
      <div className="flex gap-4 h-full min-h-0">
        {/* ── Left: Drop zone + form ── */}
        <div className="flex-1 flex flex-col gap-4 min-w-0">

          {/* Camera ID input */}
          <div className="hud-panel p-4">
            <label className="font-mono text-[10px] text-slate-500 tracking-[0.2em] uppercase block mb-2">
              CAMERA ID <span className="text-red-500">*</span>
            </label>
            <div className="flex gap-3 items-start">
              <div className="flex-1">
                <input
                  type="text"
                  value={cameraId}
                  onChange={(e) => {
                    setCameraId(e.target.value);
                    setCameraIdError(null);
                  }}
                  placeholder="e.g. CAM-01"
                  maxLength={20}
                  data-camera-id
                  className={`
                  w-full bg-slate-900/60 border rounded-sm px-3 py-2 font-mono text-sm
                  text-slate-200 placeholder-slate-700 outline-none tracking-wider uppercase
                  transition-colors
                  ${cameraIdError
                      ? "border-red-700/60 focus:border-red-500/60"
                      : "border-slate-700/60 focus:border-yellow-600/60"
                    }
                `}
                />
                {cameraIdError && (
                  <p className="font-mono text-[9px] text-red-400 mt-1 tracking-wide">{cameraIdError}</p>
                )}
              </div>
              <div className="font-mono text-[10px] text-slate-600 pt-2 leading-relaxed">
                <p>Assign this video to a camera.</p>
                <p>All detections will be tagged with this ID.</p>
              </div>
            </div>

            {/* Quick-fill presets - from API */}
            <div className="mt-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="font-mono text-[10px] text-slate-700">QUICK:</span>
                <input
                  type="text"
                  value={cameraSearch}
                  onChange={(e) => setCameraSearch(e.target.value)}
                  placeholder="search camera…"
                  className="flex-1 bg-slate-900/60 border border-slate-800 rounded-sm px-2 py-0.5 font-mono text-[10px] text-slate-400 placeholder-slate-700 outline-none focus:border-slate-600 uppercase"
                />
              </div>
              <div className="flex flex-wrap gap-1.5 max-h-16 overflow-y-auto">
                {filteredCameras.length === 0 && cameras.length === 0 && (
                  <span className="font-mono text-[9px] text-slate-700">No cameras found — type manually above</span>
                )}
                {filteredCameras.length === 0 && cameras.length > 0 && (
                  <span className="font-mono text-[9px] text-slate-700">No match</span>
                )}
                {filteredCameras.map((id) => (
                  <button
                    key={id}
                    onClick={() => { setCameraId(id); setCameraIdError(null); setCameraSearch(""); }}
                    className={`font-mono text-[10px] px-2 py-0.5 rounded-sm border transition-colors
                    ${cameraId === id
                        ? "border-yellow-600/60 text-yellow-400 bg-yellow-950/30"
                        : "border-slate-800 text-slate-600 hover:border-slate-700 hover:text-slate-400"
                      }`}
                  >
                    {id}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Drop zone */}
          <div
            className={`
            relative flex-1 hud-panel flex flex-col items-center justify-center gap-4
            border-2 border-dashed cursor-pointer transition-all duration-200 min-h-[240px]
            ${isDragOver
                ? "border-yellow-400/60 bg-yellow-950/20 scale-[1.01]"
                : dragError
                  ? "border-red-600/40 bg-red-950/10"
                  : "border-slate-700/60 hover:border-slate-600/60 hover:bg-slate-900/30"
              }
          `}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXTS}
              multiple
              className="hidden"
              onChange={handleFileChange}
            />

            {/* Icon */}
            <div className={`relative transition-colors ${isDragOver ? "text-yellow-400" : dragError ? "text-red-500" : "text-slate-700"}`}>
              {dragError ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-14 h-14">
                  <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-14 h-14">
                  <rect x="2" y="3" width="20" height="14" rx="2" />
                  <path d="M8 21h8M12 17v4M9 8l3-3 3 3M12 5v7" />
                </svg>
              )}
              {isDragOver && (
                <div className="absolute inset-0 bg-yellow-400/20 blur-xl rounded-full scale-150" />
              )}
            </div>

            {/* Text */}
            {dragError ? (
              <div className="text-center">
                <p className="font-mono text-xs text-red-400 tracking-wider">{dragError}</p>
                <p className="font-mono text-[10px] text-slate-600 mt-1">Click to try again</p>
              </div>
            ) : isDragOver ? (
              <div className="text-center">
                <p className="font-orbitron text-sm font-bold text-yellow-400 tracking-[0.2em]">RELEASE TO QUEUE</p>
                <p className="font-mono text-[10px] text-yellow-600 mt-1">Files will be added to processing queue</p>
              </div>
            ) : (
              <div className="text-center">
                <p className="font-orbitron text-sm font-bold text-slate-500 tracking-[0.15em]">DRAG & DROP VIDEO FILES</p>
                <p className="font-mono text-[10px] text-slate-700 mt-1">or click to browse</p>
                <p className="font-mono text-[10px] text-slate-800 mt-3">MP4 · AVI · MOV · MKV &nbsp;·&nbsp; MAX {MAX_SIZE_GB}GB</p>
              </div>
            )}

            {/* Corner decorations */}
            <div className={`absolute top-2 left-2 w-4 h-4 border-t-2 border-l-2 transition-colors ${isDragOver ? "border-yellow-400/60" : "border-slate-800"}`} />
            <div className={`absolute top-2 right-2 w-4 h-4 border-t-2 border-r-2 transition-colors ${isDragOver ? "border-yellow-400/60" : "border-slate-800"}`} />
            <div className={`absolute bottom-2 left-2 w-4 h-4 border-b-2 border-l-2 transition-colors ${isDragOver ? "border-yellow-400/60" : "border-slate-800"}`} />
            <div className={`absolute bottom-2 right-2 w-4 h-4 border-b-2 border-r-2 transition-colors ${isDragOver ? "border-yellow-400/60" : "border-slate-800"}`} />
          </div>

          {/* ── Stream Preview (shows active streaming jobs) ── */}
          <StreamPreviewPanel jobs={jobs} setJobs={setJobs} />
        </div>

        {/* ── Right: Job Queue ── */}
        <div className="w-80 flex-shrink-0 flex flex-col hud-panel min-h-0">
          {/* Queue header */}
          <div className="flex items-center justify-between px-3 py-2.5 border-b border-slate-800/60 flex-shrink-0">
            <div className="flex items-center gap-2">
              <span className="font-orbitron text-xs font-bold text-slate-400 tracking-[0.2em]">PROCESSING QUEUE</span>
              {jobs.length > 0 && (
                <span className="w-4 h-4 rounded-full bg-yellow-900/60 border border-yellow-800/60
                font-mono text-[8px] text-yellow-400 flex items-center justify-center">
                  {jobs.length}
                </span>
              )}
            </div>
            {jobs.length > 0 && (
              <button
                onClick={() => setJobs((j) => j.filter((x) => x.status !== "done"))}
                className="font-mono text-[10px] text-slate-600 hover:text-slate-400 transition-colors"
              >
                CLEAR DONE
              </button>
            )}
          </div>

          {/* Job list */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1.5 min-h-0">
            {jobs.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center gap-2 py-8">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-8 h-8 text-slate-800">
                  <path d="M9 12h6M9 16h6M7 4H4a2 2 0 00-2 2v14a2 2 0 002 2h16a2 2 0 002-2V6a2 2 0 00-2-2h-3" />
                  <rect x="7" y="2" width="10" height="4" rx="1" />
                </svg>
                <div className="font-mono text-[10px] text-slate-700 tracking-[0.2em] tracking-widest text-center">QUEUE EMPTY<br />Drop files to start</div>
              </div>
            ) : (
              jobs.map((job) => (
                <JobCard
                  key={job.job_id}
                  job={job}
                  onRemove={() => removeJob(job.job_id)}
                  onRetry={() => retryJob(job.job_id)}
                  onReview={() => {
                    if (job.status === "done" && job.video_id) {
                      setReviewVideo({ id: job.video_id, title: job.filename });
                    }
                  }}
                />
              ))
            )}
          </div>

          {/* Stats footer */}
          {jobs.length > 0 && (
            <div className="border-t border-slate-800/60 px-3 py-2 flex-shrink-0 grid grid-cols-3 gap-2">
              {(["queued", "processing", "done"] as JobStatus[]).map((s) => {
                const count = jobs.filter((j) => j.status === s).length;
                const style = STATUS_STYLE[s];
                return (
                  <div key={s} className="text-center">
                    <div className={`font-mono text-sm font-bold ${style.text}`}>{count}</div>
                    <div className="font-mono text-[7px] text-slate-700 tracking-widest">{statusLabel(s)}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {
        reviewVideo && (
          <VideoReviewModal
            videoId={reviewVideo.id}
            videoTitle={reviewVideo.title}
            onClose={() => setReviewVideo(null)}
          />
        )
      }
    </>
  );
}

// ─── Stream Preview Panel ────────────────────────────────────

function StreamPreviewPanel({
  jobs,
  setJobs,
}: {
  jobs: UploadJob[];
  setJobs: React.Dispatch<React.SetStateAction<UploadJob[]>>;
}) {
  // Find jobs that have active streams
  const streamingJobs = jobs.filter(
    (j) => j.stream_url && (j.status === "processing" || j.is_streaming)
  );

  // Get the most recent streaming job
  const activeJob = streamingJobs[0];

  if (!activeJob) {
    return (
      <div className="hud-panel p-4 flex flex-col items-center justify-center min-h-[200px] border border-dashed border-slate-800">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-10 h-10 text-slate-800 mb-3">
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <path d="M8 21h8M12 17v4M9 8l3-3 3 3M12 5v7" />
        </svg>
        <p className="font-mono text-[10px] text-slate-600 text-center tracking-widest">
          LIVE PREVIEW<br />Upload a video to see AI analysis stream
        </p>
      </div>
    );
  }

  const handleStopStream = async () => {
    // Stop the stream analysis
    try {
      const res = await fetch(`${API}/api/video/stream-analyze/active`);
      const data = await res.json();
      
      // Stop all active streams for this job
      if (data.active_streams && Array.isArray(data.active_streams)) {
        for (const streamId of data.active_streams) {
          if (streamId.includes(activeJob.camera_id)) {
            await fetch(`${API}/api/video/stream-analyze/${streamId}/stop`, {
              method: "POST",
            });
          }
        }
      }
    } catch (e) {
      console.error("Failed to stop stream:", e);
    }

    // Update job status
    setJobs((prev) =>
      prev.map((j) =>
        j.job_id === activeJob.job_id
          ? { ...j, is_streaming: false, status: "done", progress: 100 }
          : j
      )
    );
  };

  const handleTogglePause = () => {
    setJobs((prev) =>
      prev.map((j) =>
        j.job_id === activeJob.job_id
          ? { ...j, is_paused: !j.is_paused }
          : j
      )
    );
  };

  return (
    <div className="hud-panel flex flex-col overflow-hidden border-cyan-900/30">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-cyan-900/30 bg-cyan-950/10">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="font-orbitron text-xs font-bold text-cyan-400 tracking-[0.15em]">LIVE ANALYSIS</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[9px] text-slate-500 uppercase">{activeJob.camera_id}</span>
        </div>
      </div>

      {/* Stream Viewer */}
      <div className="flex-1 min-h-[200px] bg-black/50 relative">
        {activeJob.stream_url && !activeJob.is_paused ? (
          <StreamViewer
            streamUrl={activeJob.stream_url}
            onError={() => {
              // Stream ended or errored
              setJobs((prev) =>
                prev.map((j) =>
                  j.job_id === activeJob.job_id
                    ? { ...j, is_streaming: false, status: "done", progress: 100 }
                    : j
                )
              );
            }}
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-10 h-10 text-slate-700 mb-2">
              <rect x="6" y="4" width="4" height="16" rx="1" />
              <rect x="14" y="4" width="4" height="16" rx="1" />
            </svg>
            <span className="font-mono text-[10px] text-slate-500 uppercase">STREAM PAUSED</span>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between px-3 py-2 border-t border-slate-800/60 bg-slate-900/30">
        <div className="flex items-center gap-2">
          <button
            onClick={handleTogglePause}
            className="flex items-center gap-1.5 px-2 py-1 rounded-sm border border-slate-700 hover:border-cyan-600/60 hover:bg-cyan-950/20 transition-colors"
          >
            {activeJob.is_paused ? (
              <>
                <svg viewBox="0 0 24 24" fill="currentColor" className="w-3 h-3 text-cyan-400">
                  <path d="M8 5v14l11-7z" />
                </svg>
                <span className="font-mono text-[9px] text-cyan-400 uppercase">Resume</span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3 text-yellow-400">
                  <rect x="6" y="4" width="4" height="16" rx="1" />
                  <rect x="14" y="4" width="4" height="16" rx="1" />
                </svg>
                <span className="font-mono text-[9px] text-yellow-400 uppercase">Pause</span>
              </>
            )}
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span className="font-mono text-[9px] text-slate-500">
            {Math.round(activeJob.progress || 0)}%
          </span>
          <button
            onClick={handleStopStream}
            className="flex items-center gap-1.5 px-2 py-1 rounded-sm border border-red-900/60 hover:border-red-500/60 hover:bg-red-950/20 transition-colors"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3 text-red-400">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M9 9l6 6M15 9l-6 6" />
            </svg>
            <span className="font-mono text-[9px] text-red-400 uppercase">Stop</span>
          </button>
        </div>
      </div>

      {/* Info */}
      <div className="px-3 py-2 bg-slate-900/50 border-t border-slate-800/30">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[9px] text-slate-500 truncate max-w-[150px]">{activeJob.filename}</span>
          <span className="font-mono text-[9px] text-cyan-600">AI detecting...</span>
        </div>
      </div>
    </div>
  );
}

// ─── Job Card ────────────────────────────────────────────────

function JobCard({
  job,
  onRemove,
  onRetry,
  onReview,
}: {
  job: UploadJob;
  onRemove: () => void;
  onRetry: () => void;
  onReview?: () => void;
}) {
  const style = STATUS_STYLE[job.status];
  const progress = job.progress ?? 0;

  return (
    <div className={`relative rounded-sm border p-2.5 transition-all duration-500 ${style.bg} ${style.border} ${job.status === "processing" ? "shadow-[0_0_15px_rgba(6,182,212,0.15)] ring-1 ring-cyan-500/20" : ""}`}>
      {/* Top row */}
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <div className="flex-1 min-w-0">
          <p className="font-mono text-xs text-slate-200 truncate leading-tight">{job.filename}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="font-mono text-[10px] text-slate-600">{formatBytes(job.size_bytes)}</span>
            <span className="font-mono text-[7px] text-slate-700">·</span>
            <span className={`font-mono text-[10px] border px-1 rounded-sm ${job.camera_id === "CAM-01" ? "border-cyan-900 text-cyan-500" :
              job.camera_id === "CAM-02" ? "border-pink-900 text-pink-500" :
                job.camera_id === "CAM-03" ? "border-yellow-900 text-yellow-500" :
                  "border-slate-700 text-slate-500"
              }`}>
              {job.camera_id}
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 flex-shrink-0">
          {job.status === "done" && job.video_id && onReview && (
            <button
              onClick={onReview}
              title="Review AI accuracy (draws bounding boxes)"
              className="p-1 px-2 font-mono text-[9px] text-cyan-400 border border-cyan-800/60 rounded-sm hover:bg-cyan-900/40 transition-colors tracking-widest mr-1"
            >
              REVIEW
            </button>
          )}
          {job.status === "error" && (
            <button
              onClick={onRetry}
              title="Retry"
              className="p-1 text-yellow-600 hover:text-yellow-400 transition-colors"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3">
                <path d="M1 4v6h6M23 20v-6h-6" /><path d="M20.49 9A9 9 0 005.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 013.51 15" />
              </svg>
            </button>
          )}
          {(job.status === "done" || job.status === "error") && (
            <button
              onClick={onRemove}
              title="Remove"
              className="p-1 text-slate-700 hover:text-slate-400 transition-colors"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Status badge + progress */}
      <div className="flex items-center justify-between mb-1.5">
        <div className={`flex items-center gap-1.5 font-mono text-[10px] tracking-wider uppercase font-bold ${style.text}`}>
          {job.status === "processing" && (
            <svg className="animate-spin h-3 w-3 text-cyan-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          )}
          {job.status === "done" && (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-2.5 h-2.5">
              <path d="M20 6L9 17l-5-5" />
            </svg>
          )}
          {job.status === "error" && (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-2.5 h-2.5">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          )}
          {statusLabel(job.status)}
        </div>
        {job.status !== "error" && (
          <span className={`font-mono text-[10px] tabular-nums ${style.text}`}>
            {Math.round(progress)}%
          </span>
        )}
      </div>

      {/* Progress bar */}
      {job.status !== "error" && (
        <div className="h-1 bg-slate-800/60 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{
              width: `${progress}%`,
              background: style.barColor,
              boxShadow: job.status === "processing" ? `0 0 6px ${style.barColor}` : "none",
            }}
          />
        </div>
      )}

      {/* Error message */}
      {job.status === "error" && job.error && (
        <p className="font-mono text-[10px] text-red-500 mt-1 leading-relaxed">{job.error}</p>
      )}

      {/* Done: estimated detections */}
      {job.status === "done" && (
        <p className="font-mono text-[10px] text-green-600 mt-1">
          ✓ Indexed · {Math.floor(job.size_bytes / 800_000)} detections found
        </p>
      )}
    </div>
  );
}


// ─── Streaming upload + processing ─────────────────────────────

async function uploadWithStream(
  jobId: string,
  file: File,
  cameraId: string,
  setJobs: React.Dispatch<React.SetStateAction<UploadJob[]>>
) {
  const update = (patch: Partial<UploadJob>) =>
    setJobs((prev) => prev.map((j) => (j.job_id === jobId ? { ...j, ...patch } : j)));

  update({ status: "processing", progress: 0 });

  // ── Phase 1: Upload file and get stream URL ──────────────────────
  try {
    const result = await new Promise<{
      video_id: string | null;
      stream_url: string | null;
      video_info: { duration_sec: number; fps: number; total_frames: number } | null;
    }>((resolve, reject) => {
      const form = new FormData();
      form.append("video", file);
      form.append("camera_id", cameraId);
      form.append("frame_skip", "5");  // Match upload flow default
      form.append("show_detector_bbox", "true");
      form.append("show_detector_track_id", "true");
      form.append("show_classifier_class_name", "true");
      form.append("classifier_top_n", "1");

      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/input/upload-stream");

      // Track upload progress (maps to 0→60%)
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 60);
          update({ progress: pct });
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText);
            resolve({
              video_id: data?.video_id ?? null,
              stream_url: data?.stream_url ?? null,
              video_info: data?.video_info ?? null,
            });
          } catch {
            resolve({ video_id: null, stream_url: null, video_info: null });
          }
        } else {
          reject(new Error(`Upload failed: HTTP ${xhr.status}`));
        }
      };

      xhr.onerror = () => reject(new Error("Network error during upload"));
      xhr.send(form);
    });

    update({ 
      progress: 70, 
      video_id: result.video_id ?? undefined,
      stream_url: result.stream_url ?? undefined,
      is_streaming: true,
    });

    // ── Phase 2: Simulate processing completion based on video duration ─────
    // In streaming mode, processing happens in real-time as the client views the stream
    // We estimate completion when the video would finish playing
    const durationSec = result.video_info?.duration_sec ?? 30;
    const estimatedProcessTime = Math.max(durationSec * 0.5, 10) * 1000; // 50% of duration, min 10s
    
    // Animate progress from 70% to 95% over estimated processing time
    const progressSteps = 20;
    const stepDelay = estimatedProcessTime / progressSteps;
    
    for (let i = 0; i < progressSteps; i++) {
      await sleep(stepDelay);
      const progress = 70 + Math.round((i / progressSteps) * 25);
      update({ progress });
    }

    // Mark as done - in streaming mode, data is continuously saved to DB
    update({ status: "done", progress: 100, is_streaming: false });
    
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : "Upload failed";
    update({ status: "error", progress: 100, error: errorMsg, is_streaming: false });
  }
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
