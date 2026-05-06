"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";

// ─── Types ─────────────────────────────────────────────────────

interface VideoJob {
  id: string;
  source: string;
  camera_id: string;
  display_mode: string;
  status: "pending" | "processing" | "paused" | "completed" | "failed" | "stopped" | "cancelled";
  priority: number;
  created_at: number;
  started_at?: number;
  completed_at?: number;
  progress_pct: number;
  frames_processed: number;
  total_frames: number;
  detections_count: number;
  error_message?: string;
  original_filename?: string;
  width?: number;
  height?: number;
  fps?: number;
  duration_sec?: number;
}

interface QueueStatus {
  current_job: VideoJob | null;
  queue: VideoJob[];
  paused: VideoJob[];
  completed: VideoJob[];
  failed: VideoJob[];
  stopped: VideoJob[];
  stats: {
    total_jobs: number;
    pending_count: number;
    processing_count: number;
    paused_count: number;
    completed_count: number;
    failed_count: number;
    stopped_count: number;
  };
}

// ─── Component ────────────────────────────────────────────────

export default function RealtimeTab() {
  const [videoPath, setVideoPath] = useState("");
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inputType, setInputType] = useState<"file" | "youtube" | "stream">("file");
  const [loadingSource, setLoadingSource] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [videoEnded, setVideoEnded] = useState(false);
  const [tempFileId, setTempFileId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const multiFileInputRef = useRef<HTMLInputElement | null>(null);
  const videoEndCheckRef = useRef<NodeJS.Timeout | null>(null);

  // Queue management state
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [isQueueLoading, setIsQueueLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"input" | "queue">("input");
  const [showAddToQueue, setShowAddToQueue] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"all" | "processing" | "pending" | "paused" | "completed" | "stopped">("all");

  // Display options
  const [showDetectorBbox, setShowDetectorBbox] = useState(true);
  const [showDetectorTrackId, setShowDetectorTrackId] = useState(true);
  const [showClassifierBbox, setShowClassifierBbox] = useState(false);
  const [showClassifierClassName, setShowClassifierClassName] = useState(true);
  const [showClassifierCount, setShowClassifierCount] = useState(false);
  const [classifierTopN, setClassifierTopN] = useState("2");
  const [displayMode, setDisplayMode] = useState<"web" | "cv2" | "background">("background");
  const [saveToDatabase, setSaveToDatabase] = useState(true);
  const [saveImages, setSaveImages] = useState(true);
  const [saveBboxImages, setSaveBboxImages] = useState(true);
  const [backgroundTaskId, setBackgroundTaskId] = useState<string | null>(null);
  const [streamId, setStreamId] = useState<string | null>(null);
  const [backgroundStatus, setBackgroundStatus] = useState<{
    status: string;
    frames_processed: number;
    total_frames: number;
    detections_count: number;
    progress_pct: number;
  } | null>(null);
  const [showLogs, setShowLogs] = useState(false);
  const [cameraId, setCameraId] = useState("");
  const [queuePriority, setQueuePriority] = useState(0);

  // Loading state for queue actions
  const [pendingActions, setPendingActions] = useState<{
    [jobId: string]: 'pause' | 'resume' | 'stop' | 'remove' | 'start_now' | 'cancel' | 'reprocess' | 'resume_replace'
  }>({});

  // Camera dropdown state
  const [cameraList, setCameraList] = useState<Array<{ id: string; name: string; is_active: boolean }>>([]);
  const [isLoadingCameras, setIsLoadingCameras] = useState(false);
  const [showCameraDropdown, setShowCameraDropdown] = useState(false);
  const cameraDropdownRef = useRef<HTMLDivElement>(null);

  const backendUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  // Fetch cameras on mount
  useEffect(() => {
    const fetchCameras = async () => {
      setIsLoadingCameras(true);
      try {
        const response = await fetch(`${backendUrl}/api/cameras`);
        if (response.ok) {
          const data = await response.json();
          setCameraList(data.cameras || []);
        }
      } catch (err) {
        console.error("[Realtime] Failed to fetch cameras:", err);
      } finally {
        setIsLoadingCameras(false);
      }
    };
    fetchCameras();
  }, [backendUrl]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (cameraDropdownRef.current && !cameraDropdownRef.current.contains(event.target as Node)) {
        setShowCameraDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Cleanup temp file when component unmounts or streaming stops
  const cleanupTempFile = useCallback(async () => {
    if (tempFileId) {
      try {
        await fetch(`${backendUrl}/api/video/analyze/temp/${tempFileId}`, {
          method: "DELETE",
        });
        console.log("[Realtime] Temp file cleaned up:", tempFileId);
      } catch (err) {
        console.error("[Realtime] Failed to cleanup temp file:", err);
      }
      setTempFileId(null);
    }
  }, [tempFileId, backendUrl]);

  // Cleanup on component unmount
  useEffect(() => {
    return () => {
      if (tempFileId) {
        fetch(`${backendUrl}/api/video/analyze/temp/${tempFileId}`, { method: "DELETE" })
          .then(() => console.log("[Realtime] Cleanup on unmount:", tempFileId))
          .catch((err) => console.error("[Realtime] Cleanup failed on unmount:", err));
      }
      // Clear any pending intervals
      if (videoEndCheckRef.current) {
        clearInterval(videoEndCheckRef.current);
      }
    };
  }, [tempFileId, backendUrl]);

  // Reset stream state when video ends to ensure button changes back to "START STREAM"
  useEffect(() => {
    if (videoEnded) {
      setIsStreaming(false);
      setStreamUrl(null);
      // Keep videoEnded true to show the success message
    }
  }, [videoEnded]);

  // Poll background task status
  useEffect(() => {
    if (displayMode !== "background" || !backgroundTaskId || !isStreaming) return;

    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(`${backendUrl}/api/video/background-status/${backgroundTaskId}`);
        if (response.ok) {
          const status = await response.json();
          setBackgroundStatus({
            status: status.status,
            frames_processed: status.frames_processed,
            total_frames: status.total_frames,
            detections_count: status.detections_count,
            progress_pct: status.total_frames > 0
              ? Math.round((status.frames_processed / status.total_frames) * 100)
              : 0,
          });

          // If completed or failed, stop polling and reset state
          if (status.status === "completed" || status.status === "failed") {
            setIsStreaming(false);
            setVideoEnded(true);
            setBackgroundTaskId(null);
          }
        }
      } catch (err) {
        console.error("[Realtime] Failed to fetch background status:", err);
      }
    }, 600000); // 10 minutes

    return () => clearInterval(pollInterval);
  }, [backgroundTaskId, isStreaming, displayMode, backendUrl]);

  // Queue Management Functions
  const fetchQueueStatus = async () => {
    try {
      // Use /db-status to get data from database (includes all persisted jobs)
      const response = await fetch(`${backendUrl}/api/video-queue/db-status`);
      if (response.ok) {
        const status = await response.json();
        console.log('[Queue] API response:', status);
        setQueueStatus(status);
      }
    } catch (err) {
      console.error("[Realtime] Failed to fetch queue status:", err);
    }
  };

  // Conditional polling: 3s when processing, 10min when idle
  useEffect(() => {
    fetchQueueStatus();

    // Determine poll interval based on whether there's a processing job
    const hasProcessingJob = queueStatus?.current_job != null;
    const intervalMs = hasProcessingJob ? 3000 : 600000; // 3s vs 10min

    const pollInterval = setInterval(async () => {
      await fetchQueueStatus();
    }, intervalMs);

    return () => clearInterval(pollInterval);
  }, [backendUrl, queueStatus?.current_job?.id]);

  const addToQueue = async () => {
    if (selectedFiles.length === 0 && !videoPath.trim()) {
      setError("Please select at least one file or enter a URL");
      return;
    }

    setIsQueueLoading(true);
    setError(null);

    try {
      if (selectedFiles.length > 0) {
        // Upload multiple files
        for (const file of selectedFiles) {
          const formData = new FormData();
          formData.append("file", file);
          formData.append("camera_id", cameraId || "UNKNOWN");
          formData.append("display_mode", "background");
          formData.append("priority", queuePriority.toString());
          formData.append("save_to_db", "true");
          formData.append("save_images", "true");
          formData.append("save_bbox_images", "true");
          formData.append("frame_skip", "5");

          const response = await fetch(`${backendUrl}/api/video-queue/upload-add`, {
            method: "POST",
            body: formData,
          });

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Failed to add ${file.name}`);
          }
        }
      } else {
        // Add URL to queue
        const payload = {
          source: videoPath.trim(),
          camera_id: cameraId || "UNKNOWN",
          display_mode: "background",
          priority: queuePriority,
        };

        const response = await fetch(`${backendUrl}/api/video-queue/add`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to add to queue");
        }
      }

      // Reset form
      setSelectedFiles([]);
      setSelectedFile(null);
      setVideoPath("");
      setShowAddToQueue(false);

      // Refresh queue status
      await fetchQueueStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add to queue");
    } finally {
      setIsQueueLoading(false);
    }
  };

  const removeFromQueue = async (jobId: string) => {
    setPendingActions(prev => ({ ...prev, [jobId]: 'remove' }));

    try {
      const response = await fetch(`${backendUrl}/api/video-queue/remove/${jobId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        setError("Failed to remove job");
      }
    } catch (err) {
      console.error("[Realtime] Failed to remove job:", err);
      setError("Failed to remove job");
    } finally {
      setPendingActions(prev => {
        const updated = { ...prev };
        delete updated[jobId];
        return updated;
      });
      await fetchQueueStatus();
    }
  };

  const pauseJob = async (jobId: string) => {
    setPendingActions(prev => ({ ...prev, [jobId]: 'pause' }));

    try {
      const response = await fetch(`${backendUrl}/api/video-queue/pause`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to pause job' }));
        setError(errorData.detail || 'Failed to pause job');
      }
    } catch (err) {
      console.error("[Realtime] Failed to pause job:", err);
      setError("Failed to pause job");
    } finally {
      setPendingActions(prev => {
        const updated = { ...prev };
        delete updated[jobId];
        return updated;
      });
      await fetchQueueStatus();
    }
  };

  const resumeJob = async (jobId: string) => {
    setPendingActions(prev => ({ ...prev, [jobId]: 'resume' }));

    try {
      const response = await fetch(`${backendUrl}/api/video-queue/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      });

      if (!response.ok) {
        setError("Failed to resume job");
      }
    } catch (err) {
      console.error("[Realtime] Failed to resume job:", err);
      setError("Failed to resume job");
    } finally {
      setPendingActions(prev => {
        const updated = { ...prev };
        delete updated[jobId];
        return updated;
      });
      await fetchQueueStatus();
    }
  };

  const stopJob = async (jobId: string) => {
    setPendingActions(prev => ({ ...prev, [jobId]: 'stop' }));

    try {
      const response = await fetch(`${backendUrl}/api/video-queue/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      });

      if (!response.ok) {
        setError("Failed to stop job");
      }
    } catch (err) {
      console.error("[Realtime] Failed to stop job:", err);
      setError("Failed to stop job");
    } finally {
      setPendingActions(prev => {
        const updated = { ...prev };
        delete updated[jobId];
        return updated;
      });
      await fetchQueueStatus();
    }
  };

  const reorderQueue = async (jobId: string, newPosition: number) => {
    try {
      const response = await fetch(`${backendUrl}/api/video-queue/reorder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, new_position: newPosition }),
      });

      if (response.ok) {
        await fetchQueueStatus();
      }
    } catch (err) {
      console.error("[Realtime] Failed to reorder queue:", err);
    }
  };

  const clearCompleted = async () => {
    try {
      const response = await fetch(`${backendUrl}/api/video-queue/clear-completed`, {
        method: "DELETE",
      });

      if (response.ok) {
        await fetchQueueStatus();
      }
    } catch (err) {
      console.error("[Realtime] Failed to clear completed:", err);
    }
  };

  const startQueueJobImmediately = async (jobId: string) => {
    setPendingActions(prev => ({ ...prev, [jobId]: 'start_now' }));

    try {
      const response = await fetch(`${backendUrl}/api/video-queue/start-immediately`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      });

      if (!response.ok) {
        setError("Failed to start job immediately");
      }
    } catch (err) {
      console.error("[Realtime] Failed to start job immediately:", err);
      setError("Failed to start job immediately");
    } finally {
      setPendingActions(prev => {
        const updated = { ...prev };
        delete updated[jobId];
        return updated;
      });
      await fetchQueueStatus();
    }
  };

  const cancelAndRemoveJob = async (jobId: string) => {
    setPendingActions(prev => ({ ...prev, [jobId]: 'cancel' }));

    try {
      const response = await fetch(`${backendUrl}/api/video-queue/cancel-and-remove`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to cancel job' }));
        setError(errorData.detail || 'Failed to cancel job');
      }
    } catch (err) {
      console.error("[Realtime] Failed to cancel and remove job:", err);
      setError("Failed to cancel job");
    } finally {
      setPendingActions(prev => {
        const updated = { ...prev };
        delete updated[jobId];
        return updated;
      });
      await fetchQueueStatus();
    }
  };

  const reprocessVideo = async (jobId: string, startImmediately: boolean = false) => {
    setPendingActions(prev => ({ ...prev, [jobId]: 'reprocess' }));

    try {
      const response = await fetch(`${backendUrl}/api/video-queue/reprocess`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, start_immediately: startImmediately }),
      });

      if (!response.ok) {
        setError("Failed to reprocess video");
      }
    } catch (err) {
      console.error("[Realtime] Failed to reprocess video:", err);
      setError("Failed to reprocess video");
    } finally {
      setPendingActions(prev => {
        const updated = { ...prev };
        delete updated[jobId];
        return updated;
      });
      await fetchQueueStatus();
    }
  };

  const resumeAndReplace = async (jobId: string) => {
    setPendingActions(prev => ({ ...prev, [jobId]: 'resume_replace' }));

    try {
      const response = await fetch(`${backendUrl}/api/video-queue/resume-and-replace`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      });

      if (!response.ok) {
        setError("Failed to resume and replace");
      }
    } catch (err) {
      console.error("[Realtime] Failed to resume and replace:", err);
      setError("Failed to resume and replace");
    } finally {
      setPendingActions(prev => {
        const updated = { ...prev };
        delete updated[jobId];
        return updated;
      });
      await fetchQueueStatus();
    }
  };

  // Log management functions
  const toggleLogs = async () => {
    try {
      const action = showLogs ? "disable" : "enable";
      const response = await fetch(`${backendUrl}/api/logs/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, log_file: `web_${Date.now()}` }),
      });

      if (response.ok) {
        const result = await response.json();
        setShowLogs(!showLogs);
        console.log(result.message);
      } else {
        console.error("Failed to toggle logs");
      }
    } catch (error) {
      console.error("Error toggling logs:", error);
    }
  };

  const startStream = async () => {
    let resolvedUrl = "";

    // Handle different input types
    if (inputType === "file") {
      if (selectedFile) {
        setError(null);
        setLoadingSource(true);

        try {
          const formData = new FormData();
          formData.append("file", selectedFile);

          const uploadResponse = await fetch(`${backendUrl}/api/video/analyze/upload-temp`, {
            method: "POST",
            body: formData,
          });

          if (!uploadResponse.ok) {
            throw new Error("Failed to upload file");
          }

          const uploadResult = await uploadResponse.json();
          resolvedUrl = uploadResult.file_path;
          const tempMatch = uploadResult.file_path.match(/temp_([a-f0-9]+)_/);
          if (tempMatch) {
            setTempFileId(tempMatch[1]);
          }
          console.log("[Realtime] Temp file uploaded:", resolvedUrl);
        } catch (err) {
          setError("Failed to upload file. Please try again.");
          setLoadingSource(false);
          return;
        }
      } else {
        setError("Please select a file to upload");
        return;
      }
    } else {
      const input = videoPath.trim();
      if (!input) {
        setError(`Please enter a ${inputType === "youtube" ? "YouTube URL" : "streaming URL"}`);
        return;
      }

      setError(null);
      setLoadingSource(true);
      resolvedUrl = input;

      // Handle YouTube URLs
      if (inputType === "youtube") {
        try {
          const response = await fetch(`${backendUrl}/api/video/extract-youtube`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: input }),
          });

          if (!response.ok) {
            throw new Error("Failed to extract YouTube stream");
          }

          const result = await response.json();
          resolvedUrl = result.stream_url;
          console.log("YouTube stream extracted:", resolvedUrl);
        } catch (err) {
          setError("Failed to extract YouTube stream. Check URL and try again.");
          setLoadingSource(false);
          return;
        }
      }
    }

    try {
      if (displayMode === "web") {
        const params = new URLSearchParams({
          video_path: resolvedUrl,
          show_detector_bbox: String(showDetectorBbox),
          show_detector_track_id: String(showDetectorTrackId),
          show_classifier_bbox: String(showClassifierBbox),
          show_classifier_class_name: String(showClassifierClassName),
          show_classifier_count: String(showClassifierCount),
          classifier_top_n: classifierTopN,
          save_to_db: String(saveToDatabase),
          ...(saveToDatabase && { save_images: String(saveImages) }),
          ...(saveToDatabase && { save_bbox_images: String(saveBboxImages) }),
          ...(cameraId.trim() && { camera_id: cameraId.trim() }),
        });

        // Make a HEAD request first to get the stream ID
        const headResponse = await fetch(`${backendUrl}/api/video/stream-analyze?${params.toString()}`, {
          method: "HEAD",
        });
        const detectedStreamId = headResponse.headers.get("X-Stream-Id");
        if (detectedStreamId) {
          setStreamId(detectedStreamId);
        }

        const url = `${backendUrl}/api/video/stream-analyze?${params.toString()}`;
        setStreamUrl(url);
        setIsStreaming(true);
        setVideoEnded(false);

        // Start monitoring for video end - check both error and active streams
        videoEndCheckRef.current = setInterval(async () => {
          const img = document.querySelector('img[src*="stream-analyze"]') as HTMLImageElement;
          if (img) {
            img.onerror = () => {
              console.log("Stream ended - video completed (error)");
              setVideoEnded(true);
              setIsStreaming(false);
              setStreamUrl(null);
              setStreamId(null);
              if (videoEndCheckRef.current) {
                clearInterval(videoEndCheckRef.current);
                videoEndCheckRef.current = null;
              }
              cleanupTempFile();
            };
          }

          // Also poll active streams to detect natural stream end
          const currentStreamId = detectedStreamId;
          if (currentStreamId) {
            try {
              const activeResponse = await fetch(`${backendUrl}/api/video/stream-analyze/active`);
              if (activeResponse.ok) {
                const data = await activeResponse.json();
                const isStillActive = data.active_streams?.includes(currentStreamId);
                if (!isStillActive) {
                  console.log("Stream ended - video completed (inactive)");
                  setVideoEnded(true);
                  setIsStreaming(false);
                  setStreamUrl(null);
                  setStreamId(null);
                  if (videoEndCheckRef.current) {
                    clearInterval(videoEndCheckRef.current);
                    videoEndCheckRef.current = null;
                  }
                  cleanupTempFile();
                }
              }
            } catch (err) {
              // Silently ignore polling errors
            }
          }
        }, 2000);
      } else if (displayMode === "cv2") {
        // CV2 mode
        try {
          const response = await fetch(`${backendUrl}/api/video/analyze-cv2`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              video_path: resolvedUrl,
              show_detector_bbox: showDetectorBbox,
              show_detector_track_id: showDetectorTrackId,
              show_classifier_bbox: showClassifierBbox,
              show_classifier_class_name: showClassifierClassName,
              show_classifier_count: showClassifierCount,
              classifier_top_n: classifierTopN === "all" ? "all" : parseInt(classifierTopN),
              save_to_db: saveToDatabase,
              camera_id: cameraId.trim() || undefined,
              ...(saveToDatabase && { save_images: saveImages }),
              ...(saveToDatabase && { save_bbox_images: saveBboxImages }),
            }),
          });

          if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
          }

          setIsStreaming(true);
          setError(null);

          // For CV2 mode, the backend runs in a separate window and we need to poll for completion
          // Start polling every 2 seconds to check if the stream is still active
          const checkCv2End = setInterval(async () => {
            try {
              // Check active streams endpoint
              const statusResponse = await fetch(`${backendUrl}/api/active-streams`);
              if (statusResponse.ok) {
                const streams = await statusResponse.json();
                // If no active streams, the CV2 window has closed
                if (!streams.active_streams || streams.active_streams.length === 0) {
                  console.log("CV2 stream ended - resetting state");
                  setIsStreaming(false);
                  setVideoEnded(true);
                  clearInterval(checkCv2End);
                }
              }
            } catch (err) {
              // Don't log errors here as they might spam while checking
              // Just continue polling
            }
          }, 2000);

          // Store the interval ID so it can be cleared if user manually stops
          (window as any)._cv2CheckInterval = checkCv2End;
        } catch (fetchError) {
          if (fetchError instanceof TypeError && fetchError.message.includes("Failed to fetch")) {
            setError(`Cannot connect to backend server at ${backendUrl}. Please ensure the server is running.`);
          } else if (fetchError instanceof Error) {
            setError(`CV2 analysis failed: ${fetchError.message}`);
          } else {
            setError(`CV2 analysis failed: Unknown error occurred`);
          }
        }
      } else {
        // Background mode
        try {
          const response = await fetch(`${backendUrl}/api/video/analyze-background`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              video_path: resolvedUrl,
              camera_id: cameraId.trim() || undefined,
              frame_skip: 5,
              save_to_db: true, // Always save to DB in background mode
              save_images: saveImages,
              save_bbox_images: saveBboxImages,
            }),
          });

          if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
          }

          const result = await response.json();
          setBackgroundTaskId(result.task_id);
          setIsStreaming(true);
          setError(null);
          setVideoEnded(false);

          // Initialize status
          setBackgroundStatus({
            status: "starting",
            frames_processed: 0,
            total_frames: 0,
            detections_count: 0,
            progress_pct: 0,
          });
        } catch (fetchError) {
          if (fetchError instanceof TypeError && fetchError.message.includes("Failed to fetch")) {
            setError(`Cannot connect to backend server at ${backendUrl}. Please ensure the server is running.`);
          } else if (fetchError instanceof Error) {
            setError(`Background analysis failed: ${fetchError.message}`);
          } else {
            setError(`Background analysis failed: Unknown error occurred`);
          }
        }
      }
    } finally {
      setLoadingSource(false);
    }
  };

  const stopStream = async () => {
    // Stop active stream on backend if we have a stream ID
    if (streamId) {
      try {
        await fetch(`${backendUrl}/api/video/stream-analyze/${streamId}/stop`, {
          method: "POST",
        });
      } catch (err) {
        console.log("Failed to stop stream on backend (may already be ended):", err);
      }
    }

    setStreamUrl(null);
    setIsStreaming(false);
    setVideoEnded(false);
    setSelectedFile(null);
    setVideoPath("");
    setBackgroundTaskId(null);
    setBackgroundStatus(null);
    setStreamId(null);
    cleanupTempFile();

    // Clear video end check interval
    if (videoEndCheckRef.current) {
      clearInterval(videoEndCheckRef.current);
      videoEndCheckRef.current = null;
    }

    // Clear CV2 polling interval if exists
    if ((window as any)._cv2CheckInterval) {
      clearInterval((window as any)._cv2CheckInterval);
      (window as any)._cv2CheckInterval = null;
    }
  };


  
  return (
    <div className="grid grid-cols-3 gap-6 w-full h-full">
      {/* Left: Video Source & Basic Controls / Queue Management */}
      <div className="flex flex-col gap-4">
        {/* Tab Navigation */}
        <div className="flex gap-2">
          <button
            onClick={() => setActiveTab("input")}
            className={`flex-1 px-4 py-2 font-mono text-xs font-bold rounded-sm border transition-all ${
              activeTab === "input"
                ? "border-yellow-500/60 bg-yellow-950/30 text-yellow-400"
                : "border-slate-700 bg-slate-900/40 text-slate-500 hover:border-slate-600"
            }`}
          >
            ▶ INPUT
          </button>
          <button
            onClick={() => setActiveTab("queue")}
            className={`flex-1 px-4 py-2 font-mono text-xs font-bold rounded-sm border transition-all relative ${
              activeTab === "queue"
                ? "border-yellow-500/60 bg-yellow-950/30 text-yellow-400"
                : "border-slate-700 bg-slate-900/40 text-slate-500 hover:border-slate-600"
            }`}
          >
            🎬 QUEUE
            {queueStatus && (queueStatus.stats.pending_count + queueStatus.stats.processing_count) > 0 && (
              <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full text-white text-[10px] flex items-center justify-center">
                {queueStatus.stats.pending_count + queueStatus.stats.processing_count}
              </span>
            )}
          </button>
        </div>

        {activeTab === "input" ? (
          <SettingsCard title="VIDEO SOURCE">
          <FieldLabel>Input Type</FieldLabel>
          <div className="grid grid-cols-3 gap-3">
            <InputTypeButton
              active={inputType === "file"}
              onClick={() => setInputType("file")}
              label="📁 LOCAL FILE"
            />
            <InputTypeButton
              active={inputType === "youtube"}
              onClick={() => setInputType("youtube")}
              label="🎥 YOUTUBE"
            />
            <InputTypeButton
              active={inputType === "stream"}
              onClick={() => setInputType("stream")}
              label="🌐 STREAM URL"
            />
          </div>

          <FieldLabel>Display Mode</FieldLabel>
          <div className="grid grid-cols-3 gap-3">
            <InputTypeButton
              active={displayMode === "web"}
              onClick={() => setDisplayMode("web")}
              label="🌐 WEB"
            />
            <InputTypeButton
              active={displayMode === "cv2"}
              onClick={() => setDisplayMode("cv2")}
              label="🖥️ CV2"
            />
            <InputTypeButton
              active={displayMode === "background"}
              onClick={() => {
                setDisplayMode("background");
                // Auto-enable save to database when background mode is selected
                if (!saveToDatabase) setSaveToDatabase(true);
              }}
              label="⚡ BACKGROUND"
            />
          </div>
          <p className="font-mono text-xs text-slate-500 mt-2">
            {displayMode === "web"
              ? "Stream to web browser"
              : displayMode === "cv2"
              ? "Open separate window on server (requires GUI)"
              : "Process silently, save to database only"}
          </p>

          <div className="mt-4">
            <FieldLabel>
              {inputType === "file" ? "Video File" : inputType === "youtube" ? "YouTube URL" : "Streaming URL"}
            </FieldLabel>
          </div>

          {inputType === "file" ? (
            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    setSelectedFile(file);
                    setVideoPath(file.name);
                    setError(null);
                  }
                }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="w-full bg-slate-900/60 border border-slate-700/60 rounded-sm px-3 py-2.5 font-mono text-sm text-slate-300 outline-none focus:border-yellow-500/60 hover:border-yellow-500/40 transition-all text-left"
              >
                {selectedFile ? `📁 ${selectedFile.name}` : "📁 Click to select video file..."}
              </button>
              {selectedFile && (
                <p className="font-mono text-xs text-slate-500 mt-2">
                  Size: {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                </p>
              )}
              {selectedFile && (
                <p className="font-mono text-xs text-slate-500 mt-2">
                  ℹ️ Video file is uploaded temporarily for processing only and will not be saved to server.
                </p>
              )}
            </div>
          ) : (
            <input
              type="text"
              value={videoPath}
              onChange={(e) => setVideoPath(e.target.value)}
              placeholder={
                inputType === "youtube"
                  ? "https://www.youtube.com/watch?v=... or https://youtu.be/..."
                  : "https://example.com/stream.m3u8 or rtmp://..."
              }
              className="w-full bg-slate-900/60 border border-slate-700/60 rounded-sm px-3 py-2.5 font-mono text-sm text-slate-300 outline-none focus:border-yellow-500/60"
            />
          )}

          {inputType === "youtube" && (
            <p className="font-mono text-xs text-slate-500 mt-2">
              Supports YouTube videos and shorts. Live streams may have delays.
            </p>
          )}

          {inputType === "stream" && (
            <p className="font-mono text-xs text-slate-500 mt-2">
              Supports .m3u8, .mp4 direct links, RTMP, and other streaming protocols.
            </p>
          )}

          <div className="mt-4" ref={cameraDropdownRef}>
            <FieldLabel>Camera ID (Optional)</FieldLabel>
            <div className="relative">
              <input
                type="text"
                value={cameraId}
                onChange={(e) => {
                  setCameraId(e.target.value);
                  setShowCameraDropdown(true);
                }}
                onFocus={() => setShowCameraDropdown(true)}
                placeholder="e.g., CAM-01, FrontDoor, ParkingLot-A"
                className="w-full bg-slate-900/60 border border-slate-700/60 rounded-sm px-3 py-2.5 pr-10 font-mono text-sm text-slate-300 outline-none focus:border-yellow-500/60"
              />
              <button
                type="button"
                onClick={() => setShowCameraDropdown(!showCameraDropdown)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-500 hover:text-slate-300 transition-colors"
              >
                <svg
                  className={`w-4 h-4 transition-transform ${showCameraDropdown ? "rotate-180" : ""}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* Dropdown */}
              {showCameraDropdown && (
                <div className="absolute z-10 w-full mt-1 bg-slate-900 border border-slate-700 rounded-sm shadow-lg max-h-60 overflow-auto">
                  {isLoadingCameras ? (
                    <div className="px-3 py-2 text-slate-500 font-mono text-xs">Loading cameras...</div>
                  ) : cameraList.length === 0 ? (
                    <div className="px-3 py-2 text-slate-500 font-mono text-xs">No cameras found</div>
                  ) : (
                    <>
                      {cameraList
                        .filter((cam) => cam.name.toLowerCase().includes(cameraId.toLowerCase()))
                        .map((camera) => (
                          <button
                            key={camera.id}
                            type="button"
                            onClick={() => {
                              setCameraId(camera.name);
                              setShowCameraDropdown(false);
                            }}
                            className="w-full px-3 py-2 flex items-center justify-between hover:bg-slate-800 transition-colors text-left"
                          >
                            <span className="font-mono text-sm text-slate-300">{camera.name}</span>
                            <span
                              className={`text-xs font-mono ${
                                camera.is_active ? "text-green-400" : "text-slate-500"
                              }`}
                            >
                              {camera.is_active ? "● ACTIVE" : "○ INACTIVE"}
                            </span>
                          </button>
                        ))}
                      {cameraId && !cameraList.some((cam) => cam.name.toLowerCase() === cameraId.toLowerCase()) && (
                        <button
                          type="button"
                          onClick={() => setShowCameraDropdown(false)}
                          className="w-full px-3 py-2 border-t border-slate-800 hover:bg-slate-800 transition-colors text-left"
                        >
                          <span className="font-mono text-sm text-yellow-400">+ Use &quot;{cameraId}&quot; (new)</span>
                        </button>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
            <p className="font-mono text-xs text-slate-500 mt-2">
              Identifier for saving detection data to database. Required when &quot;Save to Database&quot; is enabled.
            </p>
          </div>

          <div className="flex gap-3 mt-4">
            {!isStreaming ? (
              <button
                onClick={startStream}
                disabled={loadingSource}
                className="flex-1 font-mono text-xs font-bold px-5 py-2.5 rounded-sm border border-green-500/60 bg-green-950/30 text-green-400 hover:bg-green-900/40 hover:border-green-400 transition-all tracking-widest disabled:opacity-50"
              >
                {loadingSource ? "⏳ LOADING SOURCE..." : "▶ START STREAM"}
              </button>
            ) : (
              <button
                onClick={stopStream}
                className="flex-1 font-mono text-xs font-bold px-5 py-2.5 rounded-sm border border-red-500/60 bg-red-950/30 text-red-400 hover:bg-red-900/40 hover:border-red-400 transition-all tracking-widest"
              >
                ⏹ STOP STREAM
              </button>
            )}
          </div>
          {error && <p className="font-mono text-xs text-red-400 mt-2">{error}</p>}
          {videoEnded && (
            <div className="font-mono text-xs text-green-400 border border-green-700/40 bg-green-950/20 px-3 py-2 rounded-sm mt-2">
              ✅ Video completed successfully!
              {saveToDatabase && " Data has been saved to database."}
            </div>
          )}
        </SettingsCard>
        ) : (
          <SettingsCard title="ADD TO QUEUE">
            {/* Global Status Summary */}
            {queueStatus && (
              <div className="grid grid-cols-3 gap-2 mb-4">
                <div className="bg-slate-800/50 rounded-sm p-2 text-center">
                  <div className="font-mono text-lg font-bold text-yellow-400">{queueStatus.stats.processing_count}</div>
                  <div className="font-mono text-[10px] text-slate-500">PROCESSING</div>
                </div>
                <div className="bg-slate-800/50 rounded-sm p-2 text-center">
                  <div className="font-mono text-lg font-bold text-blue-400">{queueStatus.stats.pending_count}</div>
                  <div className="font-mono text-[10px] text-slate-500">PENDING</div>
                </div>
                <div className="bg-slate-800/50 rounded-sm p-2 text-center">
                  <div className="font-mono text-lg font-bold text-green-400">{queueStatus.stats.completed_count}</div>
                  <div className="font-mono text-[10px] text-slate-500">COMPLETED</div>
                </div>
              </div>
            )}

            {/* Add to Queue Button */}
            <button
              onClick={() => setShowAddToQueue(true)}
              className="w-full font-mono text-xs font-bold px-4 py-2.5 rounded-sm border border-blue-500/60 bg-blue-950/30 text-blue-400 hover:bg-blue-900/40 hover:border-blue-400 transition-all tracking-widest mb-4"
            >
              ➕ ADD VIDEOS TO QUEUE
            </button>

            {/* Add Videos Modal */}
            {showAddToQueue && (
              <div className="bg-slate-800/50 rounded-sm p-4 space-y-3 mb-4">
                <FieldLabel>Add Multiple Videos</FieldLabel>
                <input
                  ref={multiFileInputRef}
                  type="file"
                  accept="video/*"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    const files = e.target.files;
                    if (files && files.length > 0) {
                      setSelectedFiles(Array.from(files));
                      setError(null);
                    }
                  }}
                />
                <button
                  onClick={() => multiFileInputRef.current?.click()}
                  className="w-full bg-slate-900/60 border border-slate-700/60 rounded-sm px-3 py-2.5 font-mono text-sm text-slate-300 outline-none focus:border-yellow-500/60 hover:border-yellow-500/40 transition-all text-left"
                >
                  {selectedFiles.length > 0
                    ? `📁 ${selectedFiles.length} file(s) selected`
                    : "📁 Click to select multiple video files..."}
                </button>
                {selectedFiles.length > 0 && (
                  <div className="space-y-1 max-h-24 overflow-y-auto">
                    {selectedFiles.map((file, idx) => (
                      <p key={idx} className="font-mono text-xs text-slate-500 truncate">
                        • {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
                      </p>
                    ))}
                  </div>
                )}

                <FieldLabel>Camera ID (Optional)</FieldLabel>
                                <div className="relative" ref={cameraDropdownRef}>
                  <input
                    type="text"
                    value={cameraId}
                    onChange={(e) => {
                      setCameraId(e.target.value);
                      setShowCameraDropdown(true);
                    }}
                    onFocus={() => setShowCameraDropdown(true)}
                    placeholder="e.g., CAM-01, FrontDoor, ParkingLot-A"
                    className="w-full bg-slate-900/60 border border-slate-700/60 rounded-sm px-3 py-2.5 pr-10 font-mono text-sm text-slate-300 outline-none focus:border-yellow-500/60 hover:border-yellow-500/40 transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowCameraDropdown(!showCameraDropdown)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-500 hover:text-slate-300 transition-colors"
                  >
                    <svg
                      className={`w-4 h-4 transition-transform ${showCameraDropdown ? "rotate-180" : ""}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
 
                  {/* Dropdown */}
                  {showCameraDropdown && (
                    <div className="absolute z-20 w-full mt-1 bg-slate-900 border border-slate-700 rounded-sm shadow-lg max-h-48 overflow-auto">
                      {isLoadingCameras ? (
                        <div className="px-3 py-2 text-slate-500 font-mono text-xs">Loading cameras...</div>
                      ) : cameraList.length === 0 ? (
                        <div className="px-3 py-2 text-slate-500 font-mono text-xs">No cameras found</div>
                      ) : (
                        <>
                          {cameraList
                            .filter((cam) => cam.name.toLowerCase().includes(cameraId.toLowerCase()))
                            .map((camera) => (
                              <button
                                key={camera.id}
                                type="button"
                                onClick={() => {
                                  setCameraId(camera.name);
                                  setShowCameraDropdown(false);
                                }}
                                className="w-full px-3 py-2 flex items-center justify-between hover:bg-slate-800 transition-colors text-left"
                              >
                                <span className="font-mono text-sm text-slate-300">{camera.name}</span>
                                <span
                                  className={`text-xs font-mono ${
                                    camera.is_active ? "text-green-400" : "text-slate-500"
                                  }`}
                                >
                                  {camera.is_active ? "● ACTIVE" : "○ INACTIVE"}
                                </span>
                              </button>
                            ))}
                          {cameraId && !cameraList.some((cam) => cam.name.toLowerCase() === cameraId.toLowerCase()) && (
                            <button
                              type="button"
                              onClick={() => setShowCameraDropdown(false)}
                              className="w-full px-3 py-2 border-t border-slate-800 hover:bg-slate-800 transition-colors text-left"
                            >
                              <span className="font-mono text-sm text-yellow-400">+ Use &quot;{cameraId}&quot; (new)</span>
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
                <p className="font-mono text-[10px] text-slate-500">
                  Leave empty to use auto-generated ID from filename
                </p>

                <FieldLabel>Priority</FieldLabel>
                <div className="flex gap-2">
                  {[0, 1, 2, 3, 4, 5].map((p) => (
                    <button
                      key={p}
                      onClick={() => setQueuePriority(p)}
                      className={`px-3 py-1 rounded-sm border font-mono text-xs transition-all ${
                        queuePriority === p
                          ? "border-yellow-500/60 bg-yellow-950/30 text-yellow-400"
                          : "border-slate-700 bg-slate-900/40 text-slate-500 hover:border-slate-600"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
                <p className="font-mono text-xs text-slate-500">Higher priority = earlier processing</p>

                <div className="flex gap-2 mt-3">
                  <button
                    onClick={addToQueue}
                    disabled={isQueueLoading || selectedFiles.length === 0}
                    className="flex-1 font-mono text-xs font-bold px-3 py-2 rounded-sm border border-green-500/60 bg-green-950/30 text-green-400 hover:bg-green-900/40 transition-all disabled:opacity-50"
                  >
                    {isQueueLoading ? "⏳ ADDING..." : "✓ ADD TO QUEUE"}
                  </button>
                  <button
                    onClick={() => {
                      setShowAddToQueue(false);
                      setSelectedFiles([]);
                    }}
                    className="px-3 py-2 font-mono text-xs rounded-sm border border-slate-700 text-slate-400 hover:bg-slate-800"
                  >
                    CANCEL
                  </button>
                </div>
              </div>
            )}

            {/* Hint */}
            <p className="font-mono text-xs text-slate-500 text-center">
              Queue status shown in the right panel →
            </p>
          </SettingsCard>
        )}
      </div>

      {/* Middle: Display Options & Classifier Settings */}
      <div className="flex flex-col gap-4">
        <SettingsCard title="DISPLAY OPTIONS">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs text-slate-400">Save Detection Data</span>
              <Toggle label="SAVE TO DATABASE" value={saveToDatabase} onChange={setSaveToDatabase} />
            </div>
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs text-slate-400">Show Terminal Logs</span>
              <Toggle label="SHOW LOGS" value={showLogs} onChange={toggleLogs} />
            </div>
            {saveToDatabase && (
              <>
                <div className="border-t border-slate-800/40 pt-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-slate-400">Save Person Crop Images</span>
                    <Toggle label="SAVE IMAGES" value={saveImages} onChange={setSaveImages} />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-slate-400">Save BBox Frame Images</span>
                    <Toggle label="SAVE BBOX" value={saveBboxImages} onChange={setSaveBboxImages} />
                  </div>
                </div>
                <p className="font-mono text-xs text-amber-500 border border-amber-700/40 bg-amber-950/20 px-3 py-2 rounded-sm">
                  ⚠️ Detection data will be saved to database and storage. This may increase storage usage.
                </p>
              </>
            )}
            <div className="border-t border-slate-800/40 pt-4">
              <div className="grid grid-cols-2 gap-3">
                <Toggle label="DETECTOR BBOX" value={showDetectorBbox} onChange={setShowDetectorBbox} />
                <Toggle label="TRACK ID" value={showDetectorTrackId} onChange={setShowDetectorTrackId} />
                <Toggle label="CLASSIFIER BBOX" value={showClassifierBbox} onChange={setShowClassifierBbox} />
                <Toggle label="CLASS NAME" value={showClassifierClassName} onChange={setShowClassifierClassName} />
                <Toggle label="CLASS COUNT" value={showClassifierCount} onChange={setShowClassifierCount} />
              </div>
            </div>
          </div>
        </SettingsCard>

        <SettingsCard title="CLASSIFIER SETTINGS">
          <FieldLabel>Top N Predictions</FieldLabel>
          <div className="flex gap-2">
            {["1", "2", "3", "4", "5", "6", "all"].map((n) => (
              <button
                key={n}
                onClick={() => setClassifierTopN(n)}
                className={`px-3 py-1.5 rounded-sm border font-mono text-xs transition-all ${
                  classifierTopN === n
                    ? "border-yellow-500/60 bg-yellow-950/30 text-yellow-400"
                    : "border-slate-700 bg-slate-900/40 text-slate-500 hover:border-slate-600"
                }`}
              >
                {n.toUpperCase()}
              </button>
            ))}
          </div>
          <p className="font-mono text-xs text-slate-500 mt-2">
            Number of class predictions to display (sorted by confidence)
          </p>
        </SettingsCard>
      </div>

      {/* Right: Stream Display & Info */}
      <div className="flex flex-col gap-4">
        {displayMode === "web" ? (
          <SettingsCard title="LIVE STREAM">
            <div className="relative aspect-video bg-slate-900/60 border border-slate-800 rounded-sm overflow-hidden">
              {isStreaming && streamUrl ? (
                <img
                  src={streamUrl}
                  alt="AI Analysis Stream"
                  className="w-full h-full object-contain"
                  onError={() => {
                    setError("Failed to load stream. Check video path and API.");
                    setIsStreaming(false);
                  }}
                />
              ) : (
                <div className="flex flex-col items-center justify-center h-full gap-3">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-12 h-12 text-slate-600">
                    <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  <span className="font-mono text-sm text-slate-500">Stream not active</span>
                </div>
              )}
            </div>
            <div className="mt-3 flex items-center justify-between">
              <span className="font-mono text-xs text-slate-500">{isStreaming ? "● LIVE" : "○ IDLE"}</span>
              {isStreaming && <span className="font-mono text-xs text-green-400 animate-pulse">PROCESSING</span>}
            </div>
          </SettingsCard>
        ) : displayMode === "cv2" ? (
          <SettingsCard title="CV2 WINDOW STATUS">
            <div className="bg-slate-900/60 border border-slate-800 rounded-sm p-6">
              {isStreaming ? (
                <div className="flex flex-col items-center gap-3">
                  <div className="w-12 h-12 rounded-full border-2 border-green-500/60 bg-green-950/30 flex items-center justify-center">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-6 h-6 text-green-400">
                      <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <span className="font-mono text-sm text-green-400">Window opened on server</span>
                  <p className="font-mono text-xs text-slate-500 text-center">Check the server machine for the video window</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3">
                  <div className="w-12 h-12 rounded-full border border-slate-700 bg-slate-800 flex items-center justify-center">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-6 h-6 text-slate-600">
                      <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <span className="font-mono text-sm text-slate-500">Window not active</span>
                </div>
              )}
            </div>
            <div className="mt-3 flex items-center justify-between">
              <span className="font-mono text-xs text-slate-500">{isStreaming ? "● RUNNING" : "○ STOPPED"}</span>
              {isStreaming && <span className="font-mono text-xs text-green-400 animate-pulse">WINDOW ACTIVE</span>}
            </div>
          </SettingsCard>
        ) : (
          <SettingsCard title={activeTab === "queue" ? "QUEUE STATUS" : "BACKGROUND PROCESSING"}>
            <div className="bg-slate-900/60 border border-slate-800 rounded-sm max-h-[400px]">
              {activeTab === "queue" ? (
                /* Queue Status Display - Continuous List */
                <>
                  {/* Status Filter */}
                  {queueStatus && (
                    <div className="mb-3 flex flex-wrap gap-1">
                      {[
                        { key: 'all', label: 'ALL', count: (queueStatus.current_job ? 1 : 0) + queueStatus.queue.length + queueStatus.paused.length + queueStatus.completed.length + queueStatus.stopped.length, color: 'text-slate-400 border-slate-600' },
                        { key: 'processing', label: 'PROC', count: queueStatus.current_job ? 1 : 0, color: 'text-yellow-400 border-yellow-500/60' },
                        { key: 'pending', label: 'PEND', count: queueStatus.queue.length, color: 'text-slate-300 border-slate-600' },
                        { key: 'paused', label: 'PAUSE', count: queueStatus.paused.length, color: 'text-amber-400 border-amber-500/60' },
                        { key: 'completed', label: 'DONE', count: queueStatus.completed.length, color: 'text-green-400 border-green-500/60' },
                        { key: 'stopped', label: 'STOP', count: queueStatus.stopped.length, color: 'text-red-400 border-red-500/60' },
                      ].map((filter) => (
                        <button
                          key={filter.key}
                          onClick={() => setStatusFilter(filter.key as typeof statusFilter)}
                          className={`px-2 py-1 font-mono text-[10px] rounded-sm border ${filter.color} ${
                            statusFilter === filter.key ? 'bg-slate-700/50' : 'hover:bg-slate-800/50'
                          }`}
                        >
                          {filter.label} ({filter.count})
                        </button>
                      ))}
                    </div>
                  )}

                  {/* All Jobs in Continuous List */}
                  {(() => {
                    // Combine all jobs into a single list with their status
                    const allJobs: Array<{job: VideoJob, type: 'processing' | 'pending' | 'paused' | 'completed' | 'stopped', index?: number}> = [];

                    // Current job (processing) - always first
                    if (queueStatus?.current_job && statusFilter !== 'pending' && statusFilter !== 'paused' && statusFilter !== 'completed' && statusFilter !== 'stopped') {
                      allJobs.push({ job: queueStatus.current_job, type: 'processing' });
                    }

                    // Queue (pending) jobs
                    if (statusFilter !== 'processing' && statusFilter !== 'paused' && statusFilter !== 'completed' && statusFilter !== 'stopped') {
                      queueStatus?.queue.forEach((job, idx) => {
                        allJobs.push({ job, type: 'pending', index: idx });
                      });
                    }

                    // Paused jobs
                    if (statusFilter !== 'processing' && statusFilter !== 'pending' && statusFilter !== 'completed' && statusFilter !== 'stopped') {
                      queueStatus?.paused.forEach((job) => {
                        allJobs.push({ job, type: 'paused' });
                      });
                    }

                    // Completed jobs (limited to last 10)
                    if (statusFilter !== 'processing' && statusFilter !== 'pending' && statusFilter !== 'paused' && statusFilter !== 'stopped') {
                      queueStatus?.completed.slice(0, 10).forEach((job) => {
                        allJobs.push({ job, type: 'completed' });
                      });
                    }

                    // Stopped jobs
                    if (statusFilter !== 'processing' && statusFilter !== 'pending' && statusFilter !== 'paused' && statusFilter !== 'completed') {
                      queueStatus?.stopped.forEach((job) => {
                        allJobs.push({ job, type: 'stopped' });
                      });
                    }

                    // Filter by specific status
                    const filteredJobs = statusFilter === 'all'
                      ? allJobs
                      : allJobs.filter(item => item.type === statusFilter);

                    return filteredJobs.length > 0 ? (
                      <div className="space-y-2 max-h-[300px] overflow-y-auto">
                        {filteredJobs.map((item, listIndex) => {
                          const { job, type, index } = item;
                          const isProcessing = type === 'processing';
                          const isPending = type === 'pending';
                          const isPaused = type === 'paused';
                          const isCompleted = type === 'completed';
                          const isStopped = type === 'stopped';

                          // Determine styling based on status
                          const borderColor = isProcessing ? 'border-yellow-500/40' :
                                            isPending ? 'border-slate-600' :
                                            isPaused ? 'border-amber-500/40' :
                                            isStopped ? 'border-red-500/40' :
                                            'border-green-500/30';

                          const bgColor = isProcessing ? 'bg-yellow-950/30' :
                                         isPending ? 'bg-slate-800/40' :
                                         isPaused ? 'bg-amber-950/20' :
                                         isStopped ? 'bg-red-950/20' :
                                         'bg-green-950/10';

                          const textColor = isProcessing ? 'text-yellow-400' :
                                           isPending ? 'text-slate-300' :
                                           isPaused ? 'text-amber-400' :
                                           isStopped ? 'text-red-400' :
                                           'text-green-400';

                          const statusIcon = isProcessing ? '●' :
                                            isPending ? '○' :
                                            isPaused ? '⏸' :
                                            isStopped ? '■' :
                                            '✓';

                          const pendingAction = pendingActions[job.id];
                          const isPendingAction = !!pendingAction;

                          return (
                            <div key={`${type}-${job.id}`} className={`${bgColor} border ${borderColor} rounded-sm p-3 relative`}>
                              {/* Loading Overlay */}
                              {isPendingAction && (
                                <div className="absolute inset-0 bg-slate-900/70 rounded-sm flex items-center justify-center z-10">
                                  <div className="flex items-center gap-2">
                                    <svg className="animate-spin h-4 w-4 text-yellow-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    <span className="font-mono text-xs text-yellow-400 uppercase">
                                      {pendingAction === 'pause' && 'Pausing...'}
                                      {pendingAction === 'resume' && 'Resuming...'}
                                      {pendingAction === 'resume_replace' && 'Resuming...'}
                                      {pendingAction === 'stop' && 'Stopping...'}
                                      {pendingAction === 'remove' && 'Removing...'}
                                      {pendingAction === 'cancel' && 'Cancelling...'}
                                      {pendingAction === 'start_now' && 'Starting...'}
                                      {pendingAction === 'reprocess' && 'Reprocessing...'}
                                    </span>
                                  </div>
                                </div>
                              )}

                              {/* Header: Status icon + Filename + Progress */}
                              <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2 min-w-0">
                                  <span className={`font-mono text-xs ${textColor} flex-shrink-0`}>{statusIcon}</span>
                                  <span className={`font-mono text-xs ${textColor} truncate max-w-[160px]`}>
                                    {job.original_filename || job.camera_id}
                                  </span>
                                </div>
                                <span className={`font-mono text-[10px] ${isProcessing ? 'text-yellow-500' : 'text-slate-500'} flex-shrink-0 ml-2`}>
                                  {isProcessing && `${job.progress_pct}%`}
                                  {isPaused && `${job.progress_pct}%`}
                                  {isCompleted && `${job.detections_count} detections`}
                                  {isPending && index !== undefined && `P:${job.priority}`}
                                  {isStopped && `${job.progress_pct}%`}
                                </span>
                              </div>

                              {/* Progress bar for processing/paused/stopped */}
                              {(isProcessing || isPaused || isStopped) && (
                                <div className="w-full bg-slate-800 rounded-full h-1.5 mb-3">
                                  <div
                                    className={`h-1.5 rounded-full transition-all ${isProcessing ? 'bg-yellow-500' : isPaused ? 'bg-amber-500/60' : 'bg-red-500/60'}`}
                                    style={{ width: `${job.progress_pct}%` }}
                                  />
                                </div>
                              )}

                              {/* Status-specific buttons */}
                              <div className="flex gap-2">
                                {isProcessing && (
                                  <>
                                    <button
                                      onClick={() => pauseJob(job.id)}
                                      disabled={isPendingAction}
                                      className="flex-1 px-2 py-1 font-mono text-[10px] rounded-sm border border-amber-500/60 text-amber-400 hover:bg-amber-950/30 disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                      {pendingAction === 'pause' ? '⏳ PAUSING...' : '⏸ PAUSE'}
                                    </button>
                                    <button
                                      onClick={() => cancelAndRemoveJob(job.id)}
                                      disabled={isPendingAction}
                                      className="flex-1 px-2 py-1 font-mono text-[10px] rounded-sm border border-red-500/60 text-red-400 hover:bg-red-950/30 disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                      {pendingAction === 'cancel' ? '⏳ CANCELLING...' : '⏹ CANCEL'}
                                    </button>
                                  </>
                                )}

                                {isPending && (
                                  <button
                                    onClick={() => startQueueJobImmediately(job.id)}
                                    disabled={isPendingAction}
                                    className="flex-1 px-2 py-1 font-mono text-[10px] rounded-sm border border-yellow-500/60 text-yellow-400 hover:bg-yellow-950/30 disabled:opacity-50 disabled:cursor-not-allowed"
                                    title="Stop current and start this immediately"
                                  >
                                    {pendingAction === 'start_now' ? '⏳ STARTING...' : '⚡ START NOW'}
                                  </button>
                                )}

                                {isPaused && (
                                  <button
                                    onClick={() => resumeAndReplace(job.id)}
                                    disabled={isPendingAction}
                                    className="flex-1 px-2 py-1 font-mono text-[10px] rounded-sm border border-green-500/60 text-green-400 hover:bg-green-950/30 disabled:opacity-50 disabled:cursor-not-allowed"
                                    title="Resume and replace current queue"
                                  >
                                    {pendingAction === 'resume_replace' ? '⏳ RESUMING...' : '▶ RESUME & REPLACE'}
                                  </button>
                                )}

                                {isCompleted && (
                                  <button
                                    onClick={() => reprocessVideo(job.id, true)}
                                    disabled={isPendingAction}
                                    className="flex-1 px-2 py-1 font-mono text-[10px] rounded-sm border border-blue-500/60 text-blue-400 hover:bg-blue-950/30 disabled:opacity-50 disabled:cursor-not-allowed"
                                    title="Re-process this video (replaces current queue)"
                                  >
                                    {pendingAction === 'reprocess' ? '⏳ REPROCESSING...' : '↻ RE-PROCESS'}
                                  </button>
                                )}

                                {isStopped && (
                                  <>
                                    <button
                                      onClick={() => resumeJob(job.id)}
                                      disabled={isPendingAction}
                                      className="flex-1 px-2 py-1 font-mono text-[10px] rounded-sm border border-green-500/60 text-green-400 hover:bg-green-950/30 disabled:opacity-50 disabled:cursor-not-allowed"
                                      title="Resume this stopped job"
                                    >
                                      {pendingAction === 'resume' ? '⏳ RESUMING...' : '▶ RESUME'}
                                    </button>
                                    <button
                                      onClick={() => removeFromQueue(job.id)}
                                      disabled={isPendingAction}
                                      className="flex-1 px-2 py-1 font-mono text-[10px] rounded-sm border border-red-500/60 text-red-400 hover:bg-red-950/30 disabled:opacity-50 disabled:cursor-not-allowed"
                                      title="Remove from queue"
                                    >
                                      {pendingAction === 'remove' ? '⏳ REMOVING...' : '🗑 REMOVE'}
                                    </button>
                                  </>
                                )}
                              </div>

                              {/* Metadata row */}
                              {(job.width || job.height || job.fps) && (
                                <div className="flex items-center gap-3 mt-2 pt-2 border-t border-slate-700/50">
                                  {job.width && job.height && (
                                    <span className="font-mono text-[10px] text-slate-500">{job.width}×{job.height}</span>
                                  )}
                                  {job.fps && (
                                    <span className="font-mono text-[10px] text-slate-500">{Math.round(job.fps)}fps</span>
                                  )}
                                  {job.duration_sec && (
                                    <span className="font-mono text-[10px] text-slate-500">{Math.round(job.duration_sec)}s</span>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      /* Empty State */
                      <div className="flex flex-col items-center gap-3 py-8">
                        <div className="w-12 h-12 rounded-full border border-slate-700 bg-slate-800 flex items-center justify-center">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-6 h-6 text-slate-600">
                            <path d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                            <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                        </div>
                        <span className="font-mono text-sm text-slate-500">Queue is empty</span>
                      </div>
                    );
                  })()}

                  {/* Clear completed button at bottom if there are completed jobs */}
                  {queueStatus && queueStatus.completed.length > 0 && (
                    <div className="mt-3 flex items-center justify-between">
                      <span className="font-mono text-[10px] text-slate-500">
                        {queueStatus.completed.length} completed
                      </span>
                      <button
                        onClick={clearCompleted}
                        className="font-mono text-[10px] text-slate-500 hover:text-red-400"
                      >
                        Clear All
                      </button>
                    </div>
                  )}
                </>
              ) : (
                /* Original Background Processing Display */
                <>
                  {isStreaming && backgroundStatus ? (
                    <div className="space-y-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full border-2 border-yellow-500/60 bg-yellow-950/30 flex items-center justify-center animate-pulse">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5 text-yellow-400">
                            <path d="M13 10V3L4 14h7v7l9-11h-7z" />
                          </svg>
                        </div>
                        <div>
                          <span className="font-mono text-sm text-yellow-400">
                            {backgroundStatus.status === "starting" ? "STARTING..." : "PROCESSING..."}
                          </span>
                          <p className="font-mono text-xs text-slate-500">No display, saving to database</p>
                        </div>
                      </div>

                      {/* Progress bar */}
                      <div className="space-y-2">
                        <div className="flex justify-between font-mono text-xs">
                          <span className="text-slate-400">Progress</span>
                          <span className="text-yellow-400">{backgroundStatus.progress_pct}%</span>
                        </div>
                        <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-yellow-500/60 transition-all duration-500"
                            style={{ width: `${backgroundStatus.progress_pct}%` }}
                          />
                        </div>
                      </div>

                      {/* Stats */}
                      <div className="grid grid-cols-2 gap-3 pt-2">
                        <div className="bg-slate-800/50 rounded-sm p-2">
                          <span className="font-mono text-xs text-slate-500">Frames</span>
                          <p className="font-mono text-sm text-slate-300">
                            {backgroundStatus.frames_processed.toLocaleString()}
                            {backgroundStatus.total_frames > 0 && ` / ${backgroundStatus.total_frames.toLocaleString()}`}
                          </p>
                        </div>
                        <div className="bg-slate-800/50 rounded-sm p-2">
                          <span className="font-mono text-xs text-slate-500">Detections</span>
                          <p className="font-mono text-sm text-slate-300">{backgroundStatus.detections_count.toLocaleString()}</p>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-3">
                      <div className="w-12 h-12 rounded-full border border-slate-700 bg-slate-800 flex items-center justify-center">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-6 h-6 text-slate-600">
                          <path d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                      </div>
                      <span className="font-mono text-sm text-slate-500">Background processing idle</span>
                    </div>
                  )}
                </>
              )}
            </div>
            {/* <div className="mt-3 flex items-center justify-between">
              {activeTab === "queue" ? (
                <>
                  <span className="font-mono text-xs text-slate-500">
                    {queueStatus?.current_job ? "● PROCESSING" : "○ IDLE"}
                  </span>
                  {queueStatus && (queueStatus.queue.length + queueStatus.paused.length) > 0 && (
                    <span className="font-mono text-xs text-yellow-400">
                      {queueStatus.queue.length + queueStatus.paused.length} pending
                    </span>
                  )}
                </>
              ) : (
                <>
                  <span className="font-mono text-xs text-slate-500">{isStreaming ? "● RUNNING" : "○ STOPPED"}</span>
                  {isStreaming && <span className="font-mono text-xs text-yellow-400 animate-pulse">PROCESSING</span>}
                </>
              )}
            </div> */}
          </SettingsCard>
        )}

        {displayMode === "cv2" && (
          <SettingsCard title="CV2 MODE INFO">
            <div className="space-y-2 font-mono text-xs text-slate-400">
              <p>• Window opens on the server machine</p>
              <p>• Requires GUI environment on server</p>
              <p>• Press &apos;q&apos; in window to stop</p>
              <p>• Higher performance than web streaming</p>
            </div>
          </SettingsCard>
        )}

        {displayMode === "background" && (
          <SettingsCard title="QUEUE MODE INFO">
            <div className="space-y-2 font-mono text-xs text-slate-400">
              <p>• Uses video queue for background processing</p>
              <p>• Switch to QUEUE tab to view status</p>
              <p>• Can pause, resume, or stop jobs</p>
              <p>• Priority system for job ordering</p>
              <p>• Automatically saves to database</p>
            </div>
          </SettingsCard>
        )}

        {displayMode !== "background" && (
          <SettingsCard title="LEGEND">
            <div className="space-y-2 font-mono text-xs">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-green-500 bg-green-500/20" />
                <span className="text-slate-400">Detector Bounding Box</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 border border-fuchsia-500 bg-fuchsia-500/20" />
                <span className="text-slate-400">Classifier Bounding Box</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-200 bg-slate-800 px-2 py-0.5">ID:1</span>
                <span className="text-slate-400">Track ID</span>
              </div>
            </div>
          </SettingsCard>
        )}
      </div>
    </div>
  );
}

// ─── Shared UI Components ───────────────────────────────────────

function SettingsCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="hud-panel p-5 flex flex-col gap-3">
      <div className="flex items-center gap-3 mb-1">
        <div className="font-mono text-xs tracking-[0.25em] text-yellow-500 font-bold">◈ {title}</div>
      </div>
      {children}
    </div>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-xs text-slate-500 tracking-widest mb-1.5 uppercase font-semibold">{children}</div>;
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={() => onChange(!value)} className="flex items-center gap-3 group transition-all">
      <div
        className={`relative w-10 h-5 rounded-full border transition-colors ${
          value ? "border-yellow-500/60 bg-yellow-950/40" : "border-slate-700 bg-slate-900"
        }`}
      >
        <div
          className={`absolute top-0.5 w-4 h-4 rounded-full transition-all ${
            value ? "left-5 bg-yellow-400" : "left-0.5 bg-slate-600"
          }`}
        />
      </div>
      <span className={`font-mono text-xs tracking-widest font-semibold ${value ? "text-yellow-400" : "text-slate-500"}`}>
        {label}
      </span>
    </button>
  );
}

function InputTypeButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 rounded-sm border font-mono text-xs transition-all ${
        active
          ? "border-yellow-500/60 bg-yellow-950/30 text-yellow-400"
          : "border-slate-700 bg-slate-900/40 text-slate-500 hover:border-slate-600"
      }`}
    >
      {label}
    </button>
  );
}
