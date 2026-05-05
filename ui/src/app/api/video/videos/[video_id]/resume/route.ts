import { NextRequest, NextResponse } from "next/server";

export async function POST(
    _request: NextRequest,
    { params }: { params: Promise<{ video_id: string }> }
) {
    const { video_id } = await params;
    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

    try {
        const upstream = await fetch(`${backendUrl}/api/video/videos/${video_id}/resume`, {
            method: "POST",
        });
        const data = await upstream.json();
        return NextResponse.json(data, { status: upstream.status });
    } catch (error) {
        return NextResponse.json({ error: "Failed to resume video processing" }, { status: 500 });
    }
}
