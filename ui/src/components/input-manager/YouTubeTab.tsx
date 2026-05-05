"use client";

import React, { useState, useEffect } from "react";
import VideoReviewModal from "../dashboard/VideoReviewModal";
import { API } from "@/lib/api"; // FastAPI base URL จาก .env.local (NEXT_PUBLIC_API_URL)

// ─── Types ────────────────────────────────────────────────────
interface VideoInfo {
    title: string;
    duration: number | null;
    thumbnail: string | null;
    uploader: string | null;
}

type JobStatus = "idle" | "resolving" | "queued" | "error";

interface QueuedVideo {
    id: string;
    url: string;
    title: string;
    thumbnail: string | null;
    cameraId: string;
    status: "processing" | "queued" | "failed";
    videoId: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────
function formatDuration(seconds: number | null): string {
    if (!seconds) return "—";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    return `${m}:${String(s).padStart(2, "0")}`;
}

function extractVideoId(url: string): string | null {
    const m = url.match(/(?:v=|youtu\.be\/|shorts\/)([A-Za-z0-9_\-]{11})/);
    return m ? m[1] : null;
}

// ─── Component ────────────────────────────────────────────────
export default function YouTubeTab() {
    const [url, setUrl] = useState("");
    const [cameraId, setCameraId] = useState("");
    const [frameSkip, setFrameSkip] = useState(30);
    const [urlError, setUrlError] = useState<string | null>(null);
    const [cameraError, setCameraError] = useState<string | null>(null);
    const [status, setStatus] = useState<JobStatus>("idle");
    const [errMsg, setErrMsg] = useState<string | null>(null);
    const [preview, setPreview] = useState<VideoInfo | null>(null);
    const [queue, setQueue] = useState<QueuedVideo[]>([]);

    const [cameras, setCameras] = useState<string[]>([]);
    const [cameraSearch, setCameraSearch] = useState("");
    const [reviewVideo, setReviewVideo] = useState<{ id: string; title: string } | null>(null);

    // Initial Fetch (Camera options list)
    useEffect(() => {
        // เรียก FastAPI โดยตรง — ไม่ผ่าน Next.js proxy
        fetch(`${API}/api/cameras`)
            .then((res) => res.json())
            .then((data: { cameras: Array<{ name: string }> }) => {
                if (Array.isArray(data.cameras)) {
                    const names = data.cameras.map((c) => c.name).filter(Boolean).sort();
                    setCameras(names);
                }
            })
            .catch(console.error);
    }, []);

    // Poll Camera Status for Queue Animation
    useEffect(() => {
        if (queue.length === 0) return;
        const intervalId = setInterval(async () => {
            try {
                const res = await fetch("/api/dashboard/cameras");
                if (!res.ok) return;
                const data = await res.json();
                const activeCams: Record<string, boolean> = {};
                (data.cameras || []).forEach((c: any) => {
                    activeCams[c.name] = c.is_processing;
                });

                setQueue(currentQueue =>
                    currentQueue.map(q => {
                        // If camera name exists in dashboard and is processing, set to processing. Otherwise queued.
                        const isCamProcessing = activeCams[q.cameraId];
                        if (isCamProcessing === true) {
                            return { ...q, status: "processing" };
                        } else {
                            return { ...q, status: "queued" };
                        }
                    })
                );
            } catch (err) {
                console.error("Failed to poll queue status:", err);
            }
        }, 2000); // 2 second polling

        return () => clearInterval(intervalId);
    }, [queue.length]);

    const filteredCameras = cameraSearch.trim()
        ? cameras.filter((id) => id.toLowerCase().includes(cameraSearch.toLowerCase()))
        : cameras;

    // Derive thumbnail from URL without fetching
    const thumbId = extractVideoId(url);

    const isValidUrl = (u: string) =>
        /youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\//.test(u) || u.includes(".m3u8") || u.includes(".mp4");

    const handleSubmit = async () => {
        let valid = true;
        if (!url.trim() || !isValidUrl(url)) {
            setUrlError("Please enter a valid YouTube or raw stream URL (.m3u8, .mp4)");
            valid = false;
        } else {
            setUrlError(null);
        }
        if (!cameraId.trim()) {
            setCameraError("Camera / Source ID is required");
            valid = false;
        } else {
            setCameraError(null);
        }
        if (!valid) return;

        setStatus("resolving");
        setErrMsg(null);
        setPreview(null);

        try {
            const form = new FormData();
            form.append("youtube_url", url.trim());
            form.append("camera_id", cameraId.trim());
            form.append("frame_skip", String(frameSkip));

            const res = await fetch("/api/video/youtube", { method: "POST", body: form });
            const data = await res.json();

            if (!res.ok) {
                setStatus("error");
                setErrMsg(data.detail ?? data.error ?? "Unknown error");
                return;
            }

            setStatus("queued");
            setPreview({
                title: data.title,
                duration: data.duration,
                thumbnail: data.thumbnail,
                uploader: null,
            });
            setQueue((q) => [
                {
                    id: data.video_id ?? Date.now().toString(),
                    url: url.trim(),
                    title: data.title,
                    thumbnail: data.thumbnail,
                    cameraId: cameraId.trim(),
                    status: "processing",
                    videoId: data.video_id,
                },
                ...q,
            ]);
            // Reset form
            setUrl("");
            setCameraId("");
            setTimeout(() => setStatus("idle"), 3000);
        } catch (e) {
            setStatus("error");
            setErrMsg(String(e));
        }
    };

    return (
        <>
            <div className="flex gap-6 h-full">
                {/* ── Left: Input form ── */}
                <div className="flex-1 flex flex-col gap-4 min-w-0">
                    {/* URL input */}
                    <div className="hud-panel p-5">
                        <div className="font-orbitron text-xs font-bold text-red-400 tracking-[0.2em] mb-4 flex items-center gap-2">
                            <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                                <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 00-.79-.05 6.34 6.34 0 00-6.34 6.34 6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.33-6.34V8.69a8.18 8.18 0 004.77 1.52V6.75a4.85 4.85 0 01-1-.06z" />
                            </svg>
                            YOUTUBE VIDEO
                        </div>

                        {/* YouTube URL */}
                        <label className="font-mono text-xs text-slate-500 tracking-widest block mb-1">VIDEO URL</label>
                        <div className="relative">
                            <input
                                type="text"
                                placeholder="https://www.youtube.com/watch?v=..."
                                value={url}
                                onChange={(e) => { setUrl(e.target.value); setUrlError(null); setStatus("idle"); }}
                                className={`w-full bg-slate-900/60 border rounded-sm px-3 py-2.5 font-mono text-sm text-slate-300 outline-none transition-colors
                                ${urlError ? "border-red-500/60" : "border-slate-700/60 focus:border-red-500/50"}`}
                            />
                            {/* Live thumbnail micro-preview */}
                            {thumbId && (
                                <img
                                    src={`https://img.youtube.com/vi/${thumbId}/default.jpg`}
                                    alt="preview"
                                    className="absolute right-2 top-1 h-8 rounded-sm opacity-80"
                                />
                            )}
                        </div>
                        {urlError && <p className="font-mono text-xs text-red-400 mt-1">{urlError}</p>}

                        {/* Camera ID */}
                        <div className="mt-4">
                            <label className="font-mono text-xs text-slate-500 tracking-widest block mb-1">CAMERA / SOURCE ID</label>
                            <input
                                type="text"
                                placeholder="e.g. yt-cam-01"
                                value={cameraId}
                                onChange={(e) => { setCameraId(e.target.value); setCameraError(null); }}
                                className={`w-full bg-slate-900/60 border rounded-sm px-3 py-2.5 font-mono text-sm text-slate-300 outline-none transition-colors
                                ${cameraError ? "border-red-500/60" : "border-slate-700/60 focus:border-red-500/50"}`}
                            />
                            {cameraError && <p className="font-mono text-xs text-red-400 mt-1">{cameraError}</p>}

                            {/* Quick-fill from API */}
                            {cameras.length > 0 && (
                                <div className="mt-2">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="font-mono text-[10px] text-slate-700">QUICK:</span>
                                        <input
                                            type="text"
                                            value={cameraSearch}
                                            onChange={(e) => setCameraSearch(e.target.value)}
                                            placeholder="search camera…"
                                            className="flex-1 bg-slate-900/60 border border-slate-800 rounded-sm px-2 py-0.5 font-mono text-[10px] text-slate-500 placeholder-slate-700 outline-none focus:border-slate-600"
                                        />
                                    </div>
                                    <div className="flex flex-wrap gap-1.5 max-h-14 overflow-y-auto">
                                        {filteredCameras.length === 0 && <span className="font-mono text-[9px] text-slate-700">No match</span>}
                                        {filteredCameras.map((id) => (
                                            <button
                                                key={id}
                                                onClick={() => { setCameraId(id); setCameraError(null); setCameraSearch(""); }}
                                                className={`font-mono text-[10px] px-2 py-0.5 rounded-sm border transition-colors
                                                ${cameraId === id
                                                        ? "border-red-600/60 text-red-400 bg-red-950/30"
                                                        : "border-slate-800 text-slate-600 hover:border-slate-700 hover:text-slate-400"
                                                    }`}
                                            >
                                                {id}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Frame skip */}
                        <div className="mt-4">
                            <div className="flex items-center justify-between mb-1">
                                <label className="font-mono text-xs text-slate-500 tracking-widest">FRAME SKIP</label>
                                <span className="font-mono text-sm font-bold text-red-400">every {frameSkip}th frame</span>
                            </div>
                            <input
                                type="range" min={1} max={60} step={1} value={frameSkip}
                                onChange={(e) => setFrameSkip(Number(e.target.value))}
                                className="w-full h-1.5 appearance-none bg-slate-800 rounded-full outline-none cursor-pointer
                [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
                [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-red-400
                [&::-webkit-slider-thumb]:shadow-[0_0_8px_rgba(248,113,113,0.7)] [&::-webkit-slider-thumb]:cursor-pointer"
                            />
                            <div className="flex justify-between mt-0.5">
                                <span className="font-mono text-xs text-slate-600">1 (every frame)</span>
                                <span className="font-mono text-xs text-slate-600">60</span>
                            </div>
                        </div>

                        {/* Submit */}
                        <button
                            onClick={handleSubmit}
                            disabled={status === "resolving"}
                            className="mt-5 w-full font-mono text-sm font-bold py-3 rounded-sm border transition-all
                            border-red-500/60 bg-red-950/30 text-red-400 hover:bg-red-900/40 hover:border-red-400
                            disabled:opacity-40 disabled:cursor-not-allowed tracking-widest"
                        >
                            {status === "resolving" ? (
                                <span className="flex items-center justify-center gap-2">
                                    <span className="w-4 h-4 border border-red-400/40 border-t-red-400 rounded-full animate-spin inline-block" />
                                    RESOLVING VIDEO…
                                </span>
                            ) : status === "queued" ? (
                                "✓ QUEUED FOR PROCESSING"
                            ) : (
                                "▶ ANALYZE VIDEO"
                            )}
                        </button>

                        {/* Error */}
                        {status === "error" && errMsg && (
                            <div className="mt-3 p-3 border border-red-700/40 bg-red-950/20 rounded-sm">
                                <p className="font-mono text-xs text-red-400">{errMsg}</p>
                            </div>
                        )}
                    </div>

                    {/* Tips */}
                    <div className="hud-panel p-4">
                        <div className="font-mono text-xs text-slate-600 tracking-widest mb-3">◈ TIPS</div>
                        <ul className="space-y-2">
                            {[
                                "Works with youtube.com/watch?v=… and youtu.be/… and Shorts",
                                "Higher frame skip = faster processing, fewer detections",
                                "Age-restricted or private videos cannot be processed",
                                "Long videos (>1hr) may take significant time to analyse",
                            ].map((tip, i) => (
                                <li key={i} className="flex items-start gap-2">
                                    <span className="font-mono text-xs text-red-500/60 mt-0.5">›</span>
                                    <span className="font-mono text-xs text-slate-500">{tip}</span>
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>

                {/* ── Right: Queue ── */}
                <div className="w-80 flex flex-col gap-3 flex-shrink-0">
                    <div className="hud-panel p-4 flex-1 flex flex-col min-h-0">
                        <div className="font-mono text-xs text-slate-500 tracking-widest mb-3 flex items-center justify-between">
                            <span>◈ PROCESSING QUEUE</span>
                            <span className="text-red-400 font-bold">{queue.length}</span>
                        </div>

                        {queue.length === 0 ? (
                            <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-10 h-10 text-slate-800">
                                    <path d="M15 10l4.553-2.277A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                                </svg>
                                <p className="font-mono text-xs text-slate-700">No videos queued yet</p>
                            </div>
                        ) : (
                            <div className="flex-1 overflow-y-auto space-y-3 pr-1">
                                {queue.map((job) => (
                                    <div
                                        key={job.id}
                                        className={`border bg-slate-900/40 rounded-sm overflow-hidden transition-all duration-500
                                            ${job.status === "processing" ? "border-cyan-500/50 shadow-[0_0_15px_rgba(6,182,212,0.15)] ring-1 ring-cyan-500/20" : "border-slate-800"}`}
                                    >
                                        {job.thumbnail && (
                                            <div className="relative h-20 w-full overflow-hidden">
                                                <img src={job.thumbnail} alt={job.title} className="w-full h-full object-cover opacity-80" />
                                                {job.status === "processing" && (
                                                    <div className="absolute inset-0 bg-gradient-to-t from-slate-900/90 to-transparent flex items-end p-2">
                                                        <div className="w-full bg-slate-800/80 h-1 rounded-full overflow-hidden">
                                                            <div className="bg-cyan-400 h-full w-1/2 animate-[progress_1s_ease-in-out_infinite]" />
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                        <div className="p-3">
                                            <p className="font-mono text-xs text-slate-300 line-clamp-2 leading-snug">{job.title}</p>
                                            <div className="flex items-center justify-between mt-2">
                                                <span className="font-mono text-xs text-slate-500 bg-slate-800/50 px-1.5 py-0.5 rounded-sm">{job.cameraId}</span>
                                                <div className="flex items-center gap-2">
                                                    {job.videoId && (
                                                        <button
                                                            onClick={() => setReviewVideo({ id: job.videoId!, title: job.title })}
                                                            title="Review AI accuracy (draws bounding boxes)"
                                                            className="p-1 px-2 font-mono text-[9px] text-cyan-400 border border-cyan-800/60 rounded-sm hover:bg-cyan-900/40 transition-colors tracking-widest"
                                                        >
                                                            REVIEW
                                                        </button>
                                                    )}
                                                    <span className={`flex items-center gap-1.5 font-mono text-[10px] uppercase font-bold tracking-wider
                                                        ${job.status === 'processing' ? 'text-cyan-400' : 'text-slate-500'}`}>
                                                        {job.status === "processing" ? (
                                                            <>
                                                                <svg className="animate-spin h-3 w-3 text-cyan-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                                                </svg>
                                                                PROCESSING
                                                            </>
                                                        ) : (
                                                            <>
                                                                <span className="w-1.5 h-1.5 rounded-full bg-slate-600" />
                                                                QUEUED
                                                            </>
                                                        )}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {reviewVideo && (
                <VideoReviewModal
                    videoId={reviewVideo.id}
                    videoTitle={reviewVideo.title}
                    onClose={() => setReviewVideo(null)}
                />
            )}
        </>
    );
}
