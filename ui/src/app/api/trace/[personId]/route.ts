import { NextRequest, NextResponse } from "next/server";

/**
 * GET /api/trace/[personId]
 *
 * Returns the journey timeline for a detected person.
 * Response: { person_id, detections: TraceEvent[], thumbnail_url, cameras: string[] }
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ personId: string }> }
) {
  const { personId } = await params;

  if (!personId || typeof personId !== "string") {
    return NextResponse.json({ error: "Invalid person ID" }, { status: 400 });
  }

  try {
    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

    const controller = new AbortController();
    const timeoutMs = 10000; // 10 วินาที (ปรับตามเครือข่าย/โหลด)
    const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs);

    const backendRes = await fetch(
      `${backendUrl}/api/persons/${encodeURIComponent(personId)}/trace`,
      {
        signal: controller.signal,
        next: { revalidate: 30 },
      }
    );

    clearTimeout(timeoutHandle);

    if (backendRes.status === 404) {
      return NextResponse.json(
        { error: "Person not found" },
        { status: 404 }
      );
    }

    if (!backendRes.ok) {
      throw new Error(`Backend responded with ${backendRes.status}`);
    }

    const data = await backendRes.json();

    return NextResponse.json({
      person_id: data.person_id ?? personId,
      thumbnail_url: data.thumbnail_url ?? null,
      detections: (data.detections ?? []).map((d: TraceDetection) => ({
        id: d.id,
        camera_id: d.camera_id,
        camera_name: d.camera_name ?? d.camera_id,
        timestamp: d.timestamp,
        thumbnail_url: d.thumbnail_url ?? null,
        confidence: d.confidence ?? 0.9,
        bounding_box: d.bounding_box ?? null,
      })),
      cameras: data.cameras ?? [],
      attributes: data.attributes ?? {},
    });
  } catch (err) {
    console.error(`[trace/${personId}] Error:`, err);

    if (err instanceof Error && err.name === "AbortError") {
      return NextResponse.json(
        { error: "Trace backend request timed out" },
        { status: 504 }
      );
    }

    return NextResponse.json(
      { error: "Failed to fetch trace data" },
      { status: 500 }
    );
  }
}

interface TraceDetection {
  id: string;
  camera_id: string;
  camera_name?: string;
  timestamp: string;
  thumbnail_url?: string;
  confidence?: number;
  bounding_box?: { x: number; y: number; w: number; h: number };
}
