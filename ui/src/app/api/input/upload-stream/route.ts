import { NextRequest, NextResponse } from "next/server";

/**
 * POST /api/input/upload-stream
 *
 * Multipart form fields:
 *   - video  : File (MP4, AVI, MKV)
 *   - camera_id : string
 *   - label  : string (optional display name)
 *   - show_detector_bbox : boolean (default: true)
 *   - show_detector_track_id : boolean (default: true)
 *   - show_classifier_class_name : boolean (default: true)
 *   - classifier_top_n : number (default: 1)
 *
 * Returns: { status, camera_id, video_id, stream_url, video_info }
 */
export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const videoFile = formData.get("video") as File | null;
    const cameraId = formData.get("camera_id") as string | null;
    const label = (formData.get("label") as string | null) ?? cameraId;
    const showDetectorBBox = (formData.get("show_detector_bbox") as string | null) ?? "true";
    const showDetectorTrackId = (formData.get("show_detector_track_id") as string | null) ?? "true";
    const showClassifierClassName = (formData.get("show_classifier_class_name") as string | null) ?? "true";
    const classifierTopN = (formData.get("classifier_top_n") as string | null) ?? "1";
    const frameSkip = (formData.get("frame_skip") as string | null) ?? "1";

    // Validate required fields
    if (!videoFile) {
      return NextResponse.json(
        { error: "No video file provided" },
        { status: 400 }
      );
    }

    if (!cameraId) {
      return NextResponse.json(
        { error: "camera_id is required" },
        { status: 400 }
      );
    }

    // Validate file type
    const validVideoTypes = [
      "video/mp4",
      "video/avi",
      "video/x-msvideo",
      "video/quicktime",
      "video/x-matroska",
    ];
    if (!validVideoTypes.includes(videoFile.type)) {
      return NextResponse.json(
        { error: "Invalid video format. Supported: MP4, AVI, MOV, MKV" },
        { status: 400 }
      );
    }

    // Validate file size (max 2GB)
    const maxSize = 2 * 1024 * 1024 * 1024;
    if (videoFile.size > maxSize) {
      return NextResponse.json(
        { error: "File too large. Max 2GB." },
        { status: 400 }
      );
    }

    // Forward to backend for processing
    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

    const backendForm = new FormData();
    backendForm.append("file", videoFile);
    backendForm.append("camera_id", cameraId);
    if (label) backendForm.append("label", label);
    backendForm.append("show_detector_bbox", showDetectorBBox);
    backendForm.append("show_detector_track_id", showDetectorTrackId);
    backendForm.append("show_classifier_class_name", showClassifierClassName);
    backendForm.append("classifier_top_n", classifierTopN);
    backendForm.append("frame_skip", frameSkip);

    const backendRes = await fetch(`${backendUrl}/api/video/analyze/upload-stream`, {
      method: "POST",
      body: backendForm,
    });

    if (!backendRes.ok) {
      const errText = await backendRes.text();
      console.error("[upload-stream] Backend error:", errText);
      return NextResponse.json(
        { error: "Backend failed to prepare video for streaming" },
        { status: 502 }
      );
    }

    const data = await backendRes.json();

    // Convert relative stream_url to full URL
    const fullStreamUrl = data.stream_url 
      ? `${backendUrl}${data.stream_url}`
      : null;

    return NextResponse.json(
      {
        status: data.status ?? "ready",
        camera_id: cameraId,
        video_id: data.video_id ?? null,
        stream_url: fullStreamUrl,
        video_info: data.video_info ?? null,
        message: data.message ?? "Video ready for streaming analysis",
      },
      { status: 201 }
    );
  } catch (err) {
    console.error("[upload-stream] Unexpected error:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
