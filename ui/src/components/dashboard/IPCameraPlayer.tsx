"use client";

import { useEffect, useRef, useState } from "react";

interface IPCameraPlayerProps {
  src: string;
  className?: string;
}

export default function IPCameraPlayer({ src, className }: IPCameraPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string>(src);

  // Determine stream type immediately when component renders
  const streamType: 'direct' | 'mjpeg' | 'rtsp' | 'image' | 'unknown' = (() => {
    // console.log(`[IPCameraPlayer] 🔍 Analyzing URL: ${src}`);
    
    if (src.startsWith('rtsp://')) {
      // console.log(`[IPCameraPlayer] ✅ Detected RTSP stream`);
      return 'rtsp';
    } else if (src.includes('/mjpg') || src.includes('/mjpeg')) {
      // console.log(`[IPCameraPlayer] ✅ Detected MJPEG stream`);
      return 'mjpeg';
    } else if (src.includes(':8080/video')) {
      // IP Webcam app video stream
      // console.log(`[IPCameraPlayer] ✅ Detected IP Webcam video stream`);
      return 'mjpeg';
    } else if (src.includes(':8080/shot.jpg')) {
      // IP Webcam app single image (will be refreshed)
      // console.log(`[IPCameraPlayer] ✅ Detected IP Webcam image stream`);
      return 'image';
    } else if (src.startsWith('http://') || src.startsWith('https://')) {
      // console.log(`[IPCameraPlayer] ✅ Detected HTTP/HTTPS stream`);
      return 'direct';
    }
    // console.log(`[IPCameraPlayer] ❌ Unknown stream type`);
    return 'unknown';
  })();

  const loadingOverlay = (
    <div className="absolute inset-0 flex items-center justify-center bg-slate-900">
      <div className="text-center">
        <div className="w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin mx-auto mb-2" />
        <p className="font-mono text-xs text-cyan-400">
          {streamType === 'image' ? 'CONNECTING TO IP WEBCAM APP' : 'CONNECTING TO IP CAMERA'}
        </p>
        <p className="font-mono text-[8px] text-slate-600 mt-1">
          {streamType === 'image' ? 'IMAGE REFRESH MODE' : streamType.toUpperCase() + ' STREAM'}
        </p>
      </div>
    </div>
  );

  // Handle MJPEG streams (display as img element) — render immediately so onLoad can fire
  if (streamType === 'mjpeg') {
    return (
      <div className={`relative ${className}`} style={{ width: '100%', height: '100%' }}>
        {isLoading && loadingOverlay}
        <img
          src={src}
          alt="IP Camera MJPEG Stream"
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          onLoad={() => setIsLoading(false)}
          onError={() => {
            setError('Failed to load MJPEG stream');
            setIsLoading(false);
          }}
        />
      </div>
    );
  }

  // Handle IP Webcam app single image with refresh — render immediately
  if (streamType === 'image') {
    return (
      <div className={`relative ${className}`} style={{ width: '100%', height: '100%' }}>
        {isLoading && loadingOverlay}
        <img
          src={imageUrl}
          alt="IP Webcam App"
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          onLoad={() => setIsLoading(false)}
          onError={() => {
            setError('Failed to load IP Webcam image');
            setIsLoading(false);
          }}
        />
      </div>
    );
  }

  // For non-image stream types, show loading overlay until ready
  if (isLoading) {
    return (
      <div className={`flex items-center justify-center bg-slate-900 ${className}`}>
        {loadingOverlay}
      </div>
    );
  }

  useEffect(() => {
    setIsLoading(true);
    setError(null);

    // Handle RTSP streams immediately (no video element needed)
    if (streamType === 'rtsp') {
      setError('RTSP streams require server-side transcoding. Use START AI to process this stream.');
      setIsLoading(false);
      return;
    }

    const video = videoRef.current;
    if (!video || streamType !== 'direct') return;

    const handleCanPlay = () => {
      setIsLoading(false);
      // console.log(`[IPCameraPlayer] ✅ Stream ready for ${src} (${streamType})`);
    };

    const handleError = (e: Event) => {
      const videoElement = e.target as HTMLVideoElement;
      const errorCode = videoElement.error?.code;
      const errorMessage = videoElement.error?.message || `Error code: ${errorCode}`;
      
      setError(errorMessage);
      setIsLoading(false);
      console.error(`[IPCameraPlayer] ❌ Stream error for ${src}:`, errorMessage);
    };

    const handleLoadStart = () => {
      setIsLoading(true);
      // console.log(`[IPCameraPlayer] 🔄 Loading stream: ${src}`);
    };

    video.addEventListener('canplay', handleCanPlay);
    video.addEventListener('error', handleError);
    video.addEventListener('loadstart', handleLoadStart);

    // Set video properties for IP camera streaming
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.preload = 'metadata';

    return () => {
      video.removeEventListener('canplay', handleCanPlay);
      video.removeEventListener('error', handleError);
      video.removeEventListener('loadstart', handleLoadStart);
    };
  }, [src]);

  // image type is handled above with early return — this effect is unused
  useEffect(() => {}, [src, streamType]);



  if (error) {
    return (
      <div className={`flex items-center justify-center bg-slate-900 ${className}`}>
        <div className="text-center">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-8 h-8 text-red-500 mx-auto mb-2">
            <path d="M15 10l4.553-2.277A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          <p className="font-mono text-xs text-red-400">IP CAMERA ERROR</p>
          <p className="font-mono text-[8px] text-slate-600 mt-1">{error}</p>
          {streamType === 'rtsp' && (
            <p className="font-mono text-[8px] text-cyan-400 mt-2">Use START AI to process RTSP streams</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <video
      ref={videoRef}
      src={src}
      className={className}
      controls={false}
      style={{ width: '100%', height: '100%', objectFit: 'contain' }}
    />
  );
}
