import { NextRequest, NextResponse } from "next/server";

const BACKEND = (process.env.AI_BACKEND_URL ?? "http://127.0.0.1:8000").replace(
    "://localhost:",
    "://127.0.0.1:"
);

export async function GET() {
    const start = performance.now();
    let fetchMs = 0;
    let status = 500;
    try {
        const fetchStart = performance.now();
        const res = await fetch(`${BACKEND}/api/settings/models`, { cache: "no-store" });
        fetchMs = performance.now() - fetchStart;
        status = res.status;
        if (!res.ok) throw new Error(`Backend ${res.status}`);
        const jsonStart = performance.now();
        const data = await res.json();
        const jsonMs = performance.now() - jsonStart;
        const response = NextResponse.json(data);
        response.headers.set("X-Next-Process-Time-Ms", (performance.now() - start).toFixed(1));
        response.headers.set("X-Next-Fetch-Time-Ms", fetchMs.toFixed(1));
        response.headers.set("X-Next-Json-Time-Ms", jsonMs.toFixed(1));
        response.headers.set("X-Backend-Process-Time-Ms", res.headers.get("X-Process-Time-Ms") ?? "");
        return response;
    } catch (e) {
        return NextResponse.json({ error: String(e) }, { status: 500 });
    } finally {
        console.log(`[NEXT-API-TIME] GET /api/settings/models status=${status} duration=${(performance.now() - start).toFixed(1)}ms fetch=${fetchMs.toFixed(1)}ms backend=${BACKEND}`);
    }
}

export async function POST(req: NextRequest) {
    const start = performance.now();
    let fetchMs = 0;
    let status = 500;
    try {
        const form = await req.formData();
        const fetchStart = performance.now();
        const res = await fetch(`${BACKEND}/api/settings/models/upload`, {
            method: "POST",
            body: form,
        });
        fetchMs = performance.now() - fetchStart;
        status = res.status;
        if (!res.ok) throw new Error(`Backend ${res.status}`);
        const response = NextResponse.json(await res.json());
        response.headers.set("X-Next-Process-Time-Ms", (performance.now() - start).toFixed(1));
        response.headers.set("X-Next-Fetch-Time-Ms", fetchMs.toFixed(1));
        response.headers.set("X-Backend-Process-Time-Ms", res.headers.get("X-Process-Time-Ms") ?? "");
        return response;
    } catch (e) {
        return NextResponse.json({ error: String(e) }, { status: 500 });
    } finally {
        console.log(`[NEXT-API-TIME] POST /api/settings/models status=${status} duration=${(performance.now() - start).toFixed(1)}ms fetch=${fetchMs.toFixed(1)}ms backend=${BACKEND}`);
    }
}
