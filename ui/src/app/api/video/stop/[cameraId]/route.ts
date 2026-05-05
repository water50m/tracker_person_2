import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

export async function POST(
    _req: NextRequest,
    { params }: { params: Promise<{ cameraId: string }> }
) {
    const { cameraId } = await params;
    try {
        const res = await fetch(`${BACKEND}/api/video/stop/${encodeURIComponent(cameraId)}`, {
            method: "POST",
        });
        const data = await res.json();
        return NextResponse.json(data, { status: res.status });
    } catch (e) {
        return NextResponse.json({ error: String(e) }, { status: 500 });
    }
}
