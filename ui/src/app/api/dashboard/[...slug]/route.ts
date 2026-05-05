import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: Promise<{ slug: string[] }> }) {
    const backendUrl = process.env.AI_BACKEND_URL || "http://localhost:8000";
    const { slug } = await params;
    const slugPath = slug ? slug.join("/") : "";
    const queryParams = request.nextUrl.search;

    const targetUrl = `${backendUrl}/api/dashboard/${slugPath}${queryParams}`;

    try {
        const res = await fetch(targetUrl, {
            method: 'GET',
            headers: {
                'Accept': request.headers.get('Accept') || 'application/json',
            },
            // Note: For MJPEG stream, caching must be disabled
            cache: 'no-store',
        });

        // For MJPEG streams, we need to return the raw body as a StreamingResponse
        if (res.headers.get('content-type')?.includes('multipart/x-mixed-replace')) {
            return new NextResponse(res.body, {
                status: res.status,
                headers: {
                    'Content-Type': res.headers.get('content-type') || 'multipart/x-mixed-replace; boundary=frame',
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Connection': 'keep-alive',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                }
            });
        }

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

export async function POST(request: NextRequest, { params }: { params: Promise<{ slug: string[] }> }) {
    const backendUrl = process.env.AI_BACKEND_URL || "http://localhost:8000";
    const { slug } = await params;
    const slugPath = slug ? slug.join("/") : "";
    const queryParams = request.nextUrl.search;

    const targetUrl = `${backendUrl}/api/dashboard/${slugPath}${queryParams}`;

    try {
        const reqBody = await request.text();
        const res = await fetch(targetUrl, {
            method: 'POST',
            headers: {
                'Content-Type': request.headers.get('Content-Type') || 'application/json',
                'Accept': 'application/json',
            },
            body: reqBody || undefined,
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
