import { NextRequest } from "next/server";

export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ video_id: string }> }
) {
    const { video_id } = await params;
    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

    // Forward the request to the FastAPI backend which streams MJPEG with bboxes
    const upstream = await fetch(`${backendUrl}/api/video/videos/${video_id}/review`, {
        cache: "no-store",
    });

    const headers = new Headers(upstream.headers);

    return new Response(upstream.body, {
        status: upstream.status,
        statusText: upstream.statusText,
        headers,
    });
}
