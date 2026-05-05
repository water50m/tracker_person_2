import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
    const url = req.nextUrl.searchParams.get("url");

    if (!url) {
        return new NextResponse("Missing url parameter", { status: 400 });
    }

    try {
        const headers = new Headers();
        // Forward essential headers from the client to bypass 403 blocks tied to IP/User-Agent
        const clientUa = req.headers.get("user-agent");
        if (clientUa) headers.set("User-Agent", clientUa);

        headers.set("Accept", "*/*");
        headers.set("Origin", "https://www.youtube.com");
        headers.set("Referer", "https://www.youtube.com/");

        const response = await fetch(url, { headers });

        if (!response.ok) {
            return new NextResponse(`Proxy failed: ${response.status} ${response.statusText}`, { status: response.status });
        }

        const buffer = await response.arrayBuffer();

        // Pass through the content type (e.g., application/vnd.apple.mpegurl or video/mp2t)
        const contentType = response.headers.get("content-type") || "application/octet-stream";

        return new NextResponse(buffer, {
            headers: {
                "Content-Type": contentType,
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-store",
            },
        });
    } catch (e) {
        return new NextResponse(String(e), { status: 500 });
    }
}
