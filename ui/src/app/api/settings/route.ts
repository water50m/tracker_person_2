import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

export async function GET() {
    try {
        const res = await fetch(`${BACKEND}/api/settings`, { next: { revalidate: 0 } });
        if (!res.ok) throw new Error(`Backend ${res.status}`);
        return NextResponse.json(await res.json());
    } catch (e) {
        return NextResponse.json({ error: String(e) }, { status: 500 });
    }
}

export async function POST(req: NextRequest) {
    try {
        const body = await req.json();
        const res = await fetch(`${BACKEND}/api/settings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`Backend ${res.status}`);
        return NextResponse.json(await res.json());
    } catch (e) {
        return NextResponse.json({ error: String(e) }, { status: 500 });
    }
}
