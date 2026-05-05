import { NextResponse } from "next/server";

const BACKEND = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

export async function GET() {
    try {
        const res = await fetch(`${BACKEND}/api/video/active-streams`, { cache: "no-store" });
        return NextResponse.json(await res.json());
    } catch (e) {
        return NextResponse.json({ active: [], error: String(e) }, { status: 500 });
    }
}
