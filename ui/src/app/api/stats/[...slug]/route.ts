import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: Promise<{ slug: string[] }> }) {
    const backendUrl = process.env.AI_BACKEND_URL || "http://localhost:8000";
    const { slug } = await params;
    const slugPath = slug ? slug.join("/") : "";
    const queryParams = request.nextUrl.search;

    const targetUrl = `${backendUrl}/api/stats/${slugPath}${queryParams}`;

    try {
        const res = await fetch(targetUrl, {
            method: 'GET',
            headers: {
                'Accept': request.headers.get('Accept') || 'application/json',
            },
        });

        const data = await res.arrayBuffer();
        return new NextResponse(data, {
            status: res.status,
            headers: {
                'Content-Type': res.headers.get('content-type') || 'application/json',
            },
        });

    } catch (err: any) {
        return NextResponse.json({ error: "Backend uncreachable", details: err.message }, { status: 502 });
    }
}
