import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const form = await request.formData();
    const image = form.get("image");

    if (!(image instanceof File)) {
      return NextResponse.json({ error: "Missing image file" }, { status: 400 });
    }

    console.log(`[API] Calling detect-attributes, file: ${image.name}, size: ${(image.size / 1024).toFixed(1)}KB`);

    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

    const backendForm = new FormData();
    // Backend expects field name: file
    backendForm.append("file", image);

    const upstream = await fetch(`${backendUrl}/api/search/detect-attributes`, {
      method: "POST",
      body: backendForm,
    });

    const contentType = upstream.headers.get("content-type") ?? "";
    if (!upstream.ok) {
      const errText = await upstream.text();
      return NextResponse.json(
        { error: "Backend failed to detect attributes", detail: errText },
        { status: 502 }
      );
    }

    if (contentType.includes("application/json")) {
      const data = await upstream.json();
      return NextResponse.json(data);
    }

    const text = await upstream.text();
    return NextResponse.json({ raw: text });
  } catch (err) {
    console.error("[search/detect-attributes] Error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
