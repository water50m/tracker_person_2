"use client";

import React, { useState, useEffect } from "react";

interface VideoReviewModalProps {
    videoId: string;
    videoTitle?: string;
    onClose: () => void;
}

export default function VideoReviewModal({ videoId, videoTitle, onClose }: VideoReviewModalProps) {
    const [imgUrl, setImgUrl] = useState("");

    useEffect(() => {
        // Generate MJPEG stream URL
        setImgUrl(`/api/video/videos/${videoId}/review`);
    }, [videoId]);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-0">
            <div className="hud-panel w-full h-full bg-slate-950 flex flex-col min-h-0 border border-yellow-900/50 shadow-2xl overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-yellow-900/30 bg-slate-900/50">
                    <div className="flex items-center gap-3">
                        <span className="font-orbitron font-bold text-yellow-400 tracking-widest uppercase text-sm">
                            AI METADATA REVIEW
                        </span>
                        {videoTitle && (
                            <span className="font-mono text-[10px] text-slate-400 border-l border-slate-700 pl-3">
                                {videoTitle}
                            </span>
                        )}
                    </div>

                    <button
                        onClick={onClose}
                        className="text-slate-500 hover:text-red-400 transition-colors p-1"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5">
                            <path d="M18 6L6 18M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Video Player */}
                <div className="flex-1 min-h-0 bg-black relative flex items-center justify-center p-0">
                    {imgUrl ? (
                        <img
                            src={imgUrl}
                            alt="Review Stream"
                            className="w-full h-full object-contain border border-slate-800"
                        />
                    ) : (
                        <div className="flex flex-col items-center gap-3">
                            <div className="w-6 h-6 border-2 border-yellow-500/30 border-t-yellow-400 rounded-full animate-spin" />
                            <span className="font-mono text-xs text-yellow-500/70 tracking-widest">CONNECTING STREAM...</span>
                        </div>
                    )}

                    <div className="absolute top-6 right-6 flex items-center gap-2 px-3 py-1.5 bg-black/50 border border-slate-800 rounded-sm backdrop-blur-md">
                        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                        <span className="font-mono text-[10px] text-red-500 tracking-widest font-bold">MJPEG STREAM (BACKEND)</span>
                    </div>
                </div>

                {/* Footer */}
                <div className="px-4 py-2 border-t border-yellow-900/30 bg-slate-900/50 flex items-center justify-between">
                    <span className="font-mono text-[10px] text-slate-500">
                        Frames are rendered by the Python backend with exact bbox coordinates. Close window to stop stream.
                    </span>
                    <span className="font-mono text-[10px] text-yellow-600 font-bold">NEXUS-EYE // DEV MODE</span>
                </div>
            </div>
        </div>
    );
}
