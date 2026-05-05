import { NextRequest, NextResponse } from "next/server";

/**
 * GET  /api/input/rtsp-streams  → list all streams
 * POST /api/input/rtsp-streams  → add new stream
 */
export async function GET() {
  try {
    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";
    const res = await fetch(`${backendUrl}/api/streams`, {
      next: { revalidate: 10 },
    });

    if (!res.ok) throw new Error("Backend unavailable");

    const data = await res.json();
    return NextResponse.json({ streams: data.streams ?? [] });
  } catch {
    return NextResponse.json({ streams: [] });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { rtsp_url, camera_id, label } = body;

    // Validate
    if (!rtsp_url || !rtsp_url.startsWith("rtsp://")) {
      return NextResponse.json(
        { error: "Invalid RTSP URL. Must start with rtsp://" },
        { status: 400 }
      );
    }

    if (!camera_id) {
      return NextResponse.json(
        { error: "camera_id is required" },
        { status: 400 }
      );
    }

    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

    const res = await fetch(`${backendUrl}/api/streams`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rtsp_url, camera_id, label: label ?? camera_id }),
    });

    if (!res.ok) {
      const errText = await res.text();
      return NextResponse.json(
        { error: `Backend error: ${errText}` },
        { status: 502 }
      );
    }

    const data = await res.json();
    return NextResponse.json(data, { status: 201 });
  } catch (err) {
    console.error("[rtsp-streams POST] Error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

/**
 * DELETE /api/input/rtsp-streams?camera_id=xxx → remove stream
 */
export async function DELETE(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const cameraId = searchParams.get("camera_id");

  if (!cameraId) {
    return NextResponse.json({ error: "camera_id required" }, { status: 400 });
  }

  try {
    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";
    const res = await fetch(
      `${backendUrl}/api/streams/${encodeURIComponent(cameraId)}`,
      { method: "DELETE" }
    );

    if (!res.ok) {
      return NextResponse.json({ error: "Failed to remove stream" }, { status: 502 });
    }

    return NextResponse.json({ success: true, camera_id: cameraId });
  } catch (err) {
    console.error("[rtsp-streams DELETE] Error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
