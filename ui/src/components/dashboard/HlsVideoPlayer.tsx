import React, { useEffect, useRef } from 'react';
import Hls from 'hls.js';

interface HlsVideoPlayerProps {
    src: string;
    className?: string;
}

export default function HlsVideoPlayer({ src, className = "" }: HlsVideoPlayerProps) {
    const videoRef = useRef<HTMLVideoElement>(null);

    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;

        let hls: Hls;

        if (Hls.isSupported() && src.includes('.m3u8')) {
            hls = new Hls({
                maxMaxBufferLength: 30, // Limit memory footprint
                backBufferLength: 10,
                // Intercept all HTTP requests hls.js makes (manifest + segments)
                // and route them through our Next.js backend to bypass CORS.
                xhrSetup: (xhr, url) => {
                    const proxiedUrl = `/api/proxy/hls?url=${encodeURIComponent(url)}`;
                    xhr.open("GET", proxiedUrl, true);
                }
            });
            // Also need to load the initial source through the proxy
            const initialSource = `/api/proxy/hls?url=${encodeURIComponent(src)}`;
            hls.loadSource(initialSource);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, () => {
                video.play().catch(e => console.warn('HLS autoplay blocked:', e));
            });
        }
        // Fallback for Safari which natively supports HLS, or direct .mp4 playback
        else if (video.canPlayType('application/vnd.apple.mpegurl') || src.includes('.mp4')) {
            video.src = src;
            video.addEventListener('loadedmetadata', () => {
                video.play().catch(e => console.warn('Native autoplay blocked:', e));
            });
        }

        return () => {
            if (hls) {
                hls.destroy();
            }
        };
    }, [src]);

    return (
        <video
            ref={videoRef}
            className={`w-full h-full object-cover pointer-events-none ${className}`}
            controls={false}
            muted
            autoPlay
            playsInline
        />
    );
}
