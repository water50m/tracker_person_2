import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
    try {
        // body may be empty or { keys: string[] }
        let body: object = {};
        try { body = await req.json(); } catch { /* no body is fine */ }

        const res = await fetch(`${BACKEND}/api/settings/reset`, {
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
