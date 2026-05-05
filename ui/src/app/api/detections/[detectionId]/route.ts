import { NextRequest, NextResponse } from "next/server";

/**
 * GET /api/detections/[detectionId]
 *
 * Returns all details of a specific detection by ID.
 * Response: Detection detail with person_id, video_id, video_time_offset
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ detectionId: string }> }
) {
  const { detectionId } = await params;

  if (!detectionId || typeof detectionId !== "string") {
    return NextResponse.json({ error: "Invalid detection ID" }, { status: 400 });
  }

  try {
    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

    const backendRes = await fetch(
      `${backendUrl}/api/detections/${encodeURIComponent(detectionId)}`,
      { next: { revalidate: 30 } }
    );

    if (backendRes.status === 404) {
      return NextResponse.json(
        { error: "Detection not found" },
        { status: 404 }
      );
    }

    if (!backendRes.ok) {
      return NextResponse.json(
        { error: "Failed to fetch detection details" },
        { status: backendRes.status }
      );
    }

    const data = await backendRes.json();
    return NextResponse.json(data);

  } catch (error) {
    console.error("Error fetching detection details:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
