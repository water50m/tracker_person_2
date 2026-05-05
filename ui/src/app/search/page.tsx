"use client";

import { useState, useEffect } from "react";
import { Search, Video, Clock, Play, ArrowRight, ArrowLeft, Link2, Eye, BoxSelect, Pause, PlayCircle } from "lucide-react";
import VideoReviewModal from "@/components/dashboard/VideoReviewModal";

interface Detection {
  id: string;
  track_id: number;
  timestamp: string;
  image_url?: string;
  bbox_image_url?: string;
  category: string;
  class_name: string;
  color_profile: Record<string, number>;
  camera_id: string;
  video_id?: string;
}

interface VideoInfo {
  id: string;
  camera_id: string;
  label: string;
  filename: string;
  file_path: string;
  status: string;
  created_at: string;
}

interface CameraRelationship {
  camera_id: string;
  relationship_type: "incoming" | "outgoing";
  avg_transition_time: number | null;
  description: string;
}

// ─── Status Badge ─────────────────────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  if (status === "completed")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-mono px-2 py-1 rounded bg-green-900/40 border border-green-800/50 text-green-400">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3 h-3">
          <path d="M20 6L9 17l-5-5" />
        </svg>
        COMPLETED
      </span>
    );
  if (status === "processing")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-mono px-2 py-1 rounded bg-cyan-900/40 border border-cyan-800/50 text-cyan-400">
        <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
        PROCESSING
      </span>
    );
  if (status === "paused")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-mono px-2 py-1 rounded bg-cyan-900/40 border border-cyan-800/50 text-cyan-400">
        <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
        PROCESSING
      </span>
    );
  if (status === "paused")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-mono px-2 py-1 rounded bg-yellow-900/40 border border-yellow-800/50 text-yellow-400">
        <Pause className="w-3 h-3" />
        PAUSED
      </span>
    );
  if (status === "error")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-mono px-2 py-1 rounded bg-red-900/40 border border-red-800/50 text-red-400">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3 h-3">
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
        ERROR
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-xs font-mono px-2 py-1 rounded bg-slate-800/60 border border-slate-700/50 text-slate-500">
      <span className="w-2 h-2 rounded-full bg-slate-600" />
      {status?.toUpperCase() ?? "PENDING"}
    </span>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function SearchPage() {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [cameras, setCameras] = useState<any[]>([]);

  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCamera, setSelectedCamera] = useState("");
  // selectedVideo ใช้เฉพาะใน Detections tab
  const [selectedVideo, setSelectedVideo] = useState("");

  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"detections" | "videos">("detections");
  const [playingVideoId, setPlayingVideoId] = useState<string | null>(null);
  const [videoTimeOffset, setVideoTimeOffset] = useState<string | null>(null);
  const [reviewVideo, setReviewVideo] = useState<{ id: string; title: string } | null>(null);

  const [cameraRelationships, setCameraRelationships] = useState<CameraRelationship[]>([]);
  const [showRelationships, setShowRelationships] = useState(false);

  // ── URL params ──────────────────────────────────────────────────────────
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const videoId = p.get("video");
    const time = p.get("time");
    const camera_id = p.get("camera_id");
    const tab = p.get("tab");

    if (camera_id) setSelectedCamera(camera_id);
    if (tab === "videos") setActiveTab("videos");

    if (videoId) {
      setSelectedVideo(videoId);
      setActiveTab("videos");
      setPlayingVideoId(videoId);
      if (time) setVideoTimeOffset(time);
    }
  }, []);

  // ── Fetches ─────────────────────────────────────────────────────────────
  const fetchDetections = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/video/detections?limit=500");
      const data = await res.json();
      setDetections(Array.isArray(data) ? data : []);
    } catch {
      setDetections([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchVideos = async () => {
    try {
      const res = await fetch("/api/video/videos");
      const data = await res.json();
      setVideos(Array.isArray(data) ? data : []);
    } catch {
      setVideos([]);
    }
  };

  // Poll for background AI processing status updates
  useEffect(() => {
    if (activeTab === "videos") {
      const interval = setInterval(fetchVideos, 3000);
      return () => clearInterval(interval);
    }
  }, [activeTab]);

  const fetchCameras = async () => {
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras`
      );
      const data = await res.json();
      setCameras(Array.isArray(data.cameras) ? data.cameras : []);
    } catch {
      setCameras([]);
    }
  };

  const fetchCameraRelationships = async (cameraId: string) => {
    if (!cameraId) { setCameraRelationships([]); return; }
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/cameras/${encodeURIComponent(cameraId)}/relationships`
      );
      const data = await res.json();
      setCameraRelationships(data.relationships || []);
    } catch {
      setCameraRelationships([]);
    }
  };

  useEffect(() => {
    fetchCameras();
    fetchVideos();
    fetchDetections();
  }, []);

  useEffect(() => {
    fetchCameraRelationships(selectedCamera);
    // เมื่อเปลี่ยน camera ให้ reset video ที่เลือกไว้
    setSelectedVideo("");
  }, [selectedCamera]);

  // ── Derived lists ───────────────────────────────────────────────────────
  // Videos ที่ตรงกับ camera ที่เลือก (ใช้ใน Detections tab dropdown + Videos tab)
  const cameraVideos = videos.filter((v) =>
    selectedCamera ? v.camera_id === selectedCamera : true
  );

  // Detections filtered
  const filteredDetections = detections.filter((d) => {
    if (selectedCamera && d.camera_id !== selectedCamera) return false;
    if (selectedVideo && d.video_id !== selectedVideo) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      return (
        d.class_name.toLowerCase().includes(q) ||
        d.category.toLowerCase().includes(q) ||
        d.camera_id.toLowerCase().includes(q)
      );
    }
    return true;
  });

  // ── Helpers ─────────────────────────────────────────────────────────────
  const handleViewDetections = (videoId: string, cameraId: string) => {
    setSelectedCamera(cameraId);
    setSelectedVideo(videoId);
    setActiveTab("detections");
  };

  const handleCameraChange = (cam: string) => {
    setSelectedCamera(cam);
    // selectedVideo is reset in the useEffect above
  };

  return (
    <div className="h-full p-4 flex flex-col gap-4">

      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="flex-shrink-0">
        <h1
          className="font-orbitron text-xl font-bold text-green-400 tracking-[0.2em] uppercase glitch-text"
          data-text="SEARCH"
        >
          SEARCH
        </h1>
        <p className="font-mono text-[10px] text-slate-500 mt-0.5 tracking-widest">
          VIDEO &amp; CAMERA SEARCH · DETECTION RESULTS
        </p>
      </div>

      {/* ── Global filter bar ──────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 p-3 bg-slate-900/50 rounded-lg border border-slate-800 flex-shrink-0">
        {/* Search input */}
        <div className="flex items-center gap-2 flex-1 min-w-[180px]">
          <Search className="w-4 h-4 text-slate-500 flex-shrink-0" />
          <input
            type="text"
            placeholder="Search clothing type, category…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="flex-1 bg-transparent border-none outline-none text-sm text-slate-300 placeholder:text-slate-600"
          />
        </div>

        {/* Camera dropdown */}
        <select
          value={selectedCamera}
          onChange={(e) => handleCameraChange(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-sm text-slate-300 font-mono"
        >
          <option value="">All Cameras</option>
          {cameras.map((c) => (
            <option key={c.id} value={c.name}>{c.name}</option>
          ))}
        </select>

        {/* Tab buttons */}
        <div className="flex items-center gap-2 ml-auto">
          <button
            onClick={() => setActiveTab("detections")}
            className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${activeTab === "detections"
              ? "bg-green-600 text-white"
              : "bg-slate-800 text-slate-400 hover:bg-slate-700"
              }`}
          >
            Detections ({filteredDetections.length})
          </button>
          <button
            onClick={() => setActiveTab("videos")}
            className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${activeTab === "videos"
              ? "bg-blue-600 text-white"
              : "bg-slate-800 text-slate-400 hover:bg-slate-700"
              }`}
          >
            Videos ({cameraVideos.length})
          </button>
        </div>
      </div>

      {/* ── Camera relationships ───────────────────────────────────── */}
      {selectedCamera && cameraRelationships.length > 0 && (
        <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-3 flex-shrink-0">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Link2 className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-xs font-mono text-cyan-400 tracking-wider uppercase">
                กล้องที่สัมพันธ์กับ {selectedCamera}
              </span>
            </div>
            <button
              onClick={() => setShowRelationships(!showRelationships)}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              {showRelationships ? "ซ่อน" : "แสดง"}
            </button>
          </div>
          {showRelationships && (
            <div className="flex flex-wrap gap-2">
              {cameraRelationships.map((rel, i) => (
                <button
                  key={i}
                  onClick={() => handleCameraChange(rel.camera_id)}
                  className="inline-flex items-center gap-1.5 px-2 py-1 bg-slate-800/60 rounded border border-slate-700/50 text-xs font-mono text-cyan-300 hover:border-cyan-700/50 transition-colors"
                >
                  {rel.relationship_type === "outgoing"
                    ? <ArrowRight className="w-3 h-3 text-green-400" />
                    : <ArrowLeft className="w-3 h-3 text-blue-400" />}
                  {rel.camera_id}
                  {rel.avg_transition_time && (
                    <span className="text-slate-600 ml-1">{rel.avg_transition_time}s</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Content ────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto min-h-0">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="font-mono text-sm text-slate-500 animate-pulse tracking-widest">LOADING…</div>
          </div>

        ) : activeTab === "detections" ? (
          /* ── Detections tab ──────────────────────────────────────── */
          <div className="flex flex-col gap-4 h-full">
            {/* Sub-filter: video picker (only show for this tab) */}
            <div className="flex items-center gap-3 flex-shrink-0">
              <span className="font-mono text-[10px] text-slate-600 tracking-widest uppercase">Video</span>
              <select
                value={selectedVideo}
                onChange={(e) => setSelectedVideo(e.target.value)}
                className="bg-slate-800/80 border border-slate-700 rounded px-3 py-1.5 text-xs font-mono text-slate-300"
              >
                <option value="">
                  {selectedCamera ? `All videos (${cameraVideos.length})` : "All Videos"}
                </option>
                {cameraVideos.map((v) => (
                  <option key={v.id} value={v.id}>{v.filename}</option>
                ))}
              </select>
              {selectedVideo && (
                <button
                  onClick={() => setSelectedVideo("")}
                  className="text-xs text-slate-600 hover:text-slate-400 font-mono transition-colors"
                >
                  ✕ Clear
                </button>
              )}
              <span className="font-mono text-[10px] text-slate-700 ml-auto">
                {filteredDetections.length} results
              </span>
            </div>

            {/* Detection grid */}
            {filteredDetections.length === 0 ? (
              <div className="flex flex-col items-center justify-center flex-1 gap-3 text-center">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-10 h-10 text-slate-800">
                  <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
                </svg>
                <p className="font-mono text-sm text-slate-700 tracking-widest">NO DETECTIONS</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3 overflow-auto">
                {filteredDetections.map((d) => (
                  <div
                    key={d.id}
                    className="bg-slate-900/50 border border-slate-800 rounded-lg p-3 hover:border-slate-600 transition-colors"
                  >
                    {d.bbox_image_url || d.image_url ? (
                      <img
                        src={d.bbox_image_url || d.image_url}
                        alt={d.class_name}
                        className="w-full aspect-[2/3] object-cover object-top rounded mb-2"
                      />
                    ) : (
                      <div className="w-full aspect-[2/3] bg-slate-800/60 rounded mb-2 flex items-center justify-center">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-8 h-8 text-slate-700"><circle cx="12" cy="7" r="4" /><path d="M4 21v-1a8 8 0 0116 0v1" /></svg>
                      </div>
                    )}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-green-400">{d.camera_id}</span>
                      </div>
                      <div className="font-semibold text-sm text-slate-200">{d.class_name}</div>
                      <div className="text-xs space-y-1">
                        <div className="flex items-center gap-1">
                          <span className="text-slate-500 font-mono">1.</span>
                          <span className="text-slate-400">{d.category}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <span className="text-slate-500 font-mono">2.</span>
                          <span className="text-slate-400">{d.class_name}</span>
                        </div>
                      </div>
                      <div className="text-xs space-y-1">
                        <div className="flex items-center gap-1">
                          <span className="text-slate-500 font-mono">1.</span>
                          <span className="text-slate-400">{d.category}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <span className="text-slate-500 font-mono">2.</span>
                          <span className="text-slate-400">{d.class_name}</span>
                        </div>
                      </div>
                      <div className="text-xs text-slate-500 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(d.timestamp).toLocaleString()}
                      </div>
                      {Object.keys(d.color_profile).length > 0 && (
                        <div className="text-xs text-slate-600">
                          {Object.keys(d.color_profile).slice(0, 3).join(", ")}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        ) : (
          /* ── Videos tab ──────────────────────────────────────────── */
          <div className="space-y-2">
            {cameraVideos.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
                <Video className="w-10 h-10 text-slate-800" />
                <p className="font-mono text-sm text-slate-700 tracking-widest">
                  {selectedCamera ? `NO VIDEOS FOR ${selectedCamera}` : "NO VIDEOS"}
                </p>
              </div>
            ) : (
              cameraVideos.map((video) => (
                <div
                  key={video.id}
                  className="bg-slate-900/50 border border-slate-800 rounded-lg p-4 hover:border-slate-700 transition-colors"
                >
                  <div className="flex items-center justify-between gap-4">
                    {/* Left: info */}
                    <div className="flex items-center gap-3 min-w-0">
                      <Video className="w-5 h-5 text-blue-400 flex-shrink-0" />
                      <div className="min-w-0">
                        <div className="font-semibold text-slate-200 truncate">{video.filename}</div>
                        <div className="text-xs text-slate-500 font-mono mt-0.5">
                          {video.camera_id} · {new Date(video.created_at).toLocaleString()}
                        </div>
                      </div>
                    </div>

                    {/* Right: status + actions */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <StatusBadge status={video.status} />

                      {/* View Detections button */}
                      {video.status === "completed" && (
                        <button
                          onClick={() => handleViewDetections(video.id, video.camera_id)}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-mono rounded border border-green-800/60 text-green-400 bg-green-950/30 hover:bg-green-900/40 transition-colors"
                          title="View detections for this video"
                        >
                          <Eye className="w-3 h-3" />
                          Detections
                        </button>
                      )}

                      {/* Review Bbox Button */}
                      {video.status === "completed" && (
                        <button
                          onClick={() => setReviewVideo({ id: video.id, title: video.filename })}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-mono rounded border border-cyan-800/60 text-cyan-400 bg-cyan-950/30 hover:bg-cyan-900/40 transition-colors"
                          title="Review AI accuracy (draws bounding boxes)"
                        >
                          <BoxSelect className="w-3 h-3" />
                          Review BBox
                        </button>
                      )}

                      {/* Pause AI Processing Button */}
                      {video.status === "processing" && (
                        <button
                          onClick={() => {
                            fetch(`/api/video/videos/${video.id}/pause`, { method: "POST" }).then(fetchVideos);
                          }}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-mono rounded border border-yellow-800/60 text-yellow-400 bg-yellow-950/30 hover:bg-yellow-900/40 transition-colors"
                          title="Pause background AI processing"
                        >
                          <Pause className="w-3 h-3" />
                          Pause AI
                        </button>
                      )}

                      {/* Resume AI Processing Button */}
                      {video.status === "paused" && (
                        <button
                          onClick={() => {
                            fetch(`/api/video/videos/${video.id}/resume`, { method: "POST" }).then(fetchVideos);
                          }}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-mono rounded border border-blue-800/60 text-blue-400 bg-blue-950/30 hover:bg-blue-900/40 transition-colors"
                          title="Resume background AI processing"
                        >
                          <PlayCircle className="w-3 h-3" />
                          Resume AI
                        </button>
                      )}

                      {/* Play button */}
                      {video.status === "completed" && (
                        <button
                          onClick={() => setPlayingVideoId(playingVideoId === video.id ? null : video.id)}
                          className="p-2 bg-blue-600 hover:bg-blue-700 rounded text-white transition-colors ml-2"
                          title={playingVideoId === video.id ? "Stop Video" : "Play Video"}
                        >
                          <Play className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Inline player */}
                  {playingVideoId === video.id && (
                    <div className="mt-4 rounded-lg overflow-hidden bg-black">
                      <video
                        controls
                        autoPlay
                        className="w-full max-h-96"
                        src={`/api/video/videos/${video.id}/stream`}
                        ref={(el) => {
                          if (el && videoTimeOffset) {
                            el.addEventListener("loadedmetadata", () => {
                              el.currentTime = parseFloat(videoTimeOffset);
                            }, { once: true });
                          }
                        }}
                      >
                        Your browser does not support the video tag.
                      </video>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {reviewVideo && (
        <VideoReviewModal
          videoId={reviewVideo.id}
          videoTitle={reviewVideo.title}
          onClose={() => setReviewVideo(null)}
        />
      )}
    </div>
  );
}
