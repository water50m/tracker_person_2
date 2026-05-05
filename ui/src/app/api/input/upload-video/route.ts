import { NextRequest, NextResponse } from "next/server";

/**
 * POST /api/input/upload-video
 *
 * Multipart form fields:
 *   - video  : File (MP4, AVI, MKV)
 *   - camera_id : string
 *   - label  : string (optional display name)
 *
 * Returns: { job_id, status, camera_id, filename, size_bytes, estimated_duration_sec }
 */
export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const videoFile = formData.get("video") as File | null;
    const cameraId = formData.get("camera_id") as string | null;
    const label = (formData.get("label") as string | null) ?? cameraId;

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

    const backendRes = await fetch(`${backendUrl}/api/video/analyze/upload`, {
      method: "POST",
      body: backendForm,
    });

    if (!backendRes.ok) {
      const errText = await backendRes.text();
      console.error("[upload-video] Backend error:", errText);
      return NextResponse.json(
        { error: "Backend failed to queue video for processing" },
        { status: 502 }
      );
    }

    const data = await backendRes.json();

    return NextResponse.json(
      {
        job_id: data.job_id,
        video_id: data.video_id ?? null,
        status: data.status ?? "queued",
        camera_id: cameraId,
        filename: videoFile.name,
        size_bytes: videoFile.size,
        estimated_duration_sec: data.estimated_duration_sec ?? null,
        message: "Video queued for AI processing",
      },
      { status: 201 }
    );
  } catch (err) {
    console.error("[upload-video] Unexpected error:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
