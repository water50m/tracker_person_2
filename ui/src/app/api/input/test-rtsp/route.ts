import { NextRequest, NextResponse } from "next/server";

/**
 * POST /api/input/test-rtsp
 *
 * Body: { rtsp_url: string }
 * Returns: { reachable: boolean, latency_ms?: number, error?: string }
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { rtsp_url } = body;

    if (!rtsp_url || !rtsp_url.startsWith("rtsp://")) {
      return NextResponse.json(
        { reachable: false, error: "Invalid RTSP URL" },
        { status: 400 }
      );
    }

    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";
    const start = Date.now();

    const res = await fetch(`${backendUrl}/api/streams/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rtsp_url }),
      signal: AbortSignal.timeout(10_000), // 10 second timeout
    });

    const latency = Date.now() - start;

    if (!res.ok) {
      return NextResponse.json(
        { reachable: false, error: "Stream unreachable or authentication failed" },
        { status: 200 }
      );
    }

    const data = await res.json();
    return NextResponse.json({
      reachable: data.reachable ?? true,
      latency_ms: latency,
      resolution: data.resolution ?? null,
      fps: data.fps ?? null,
    });
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Connection test failed";
    return NextResponse.json({ reachable: false, error: message }, { status: 200 });
  }
}
