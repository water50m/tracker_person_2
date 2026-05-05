import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = searchParams.get("limit") || "20";
    const offset = searchParams.get("offset") || "0";
    const cameraId = searchParams.get("camera_id");

    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";
    
    // สร้าง query parameters สำหรับ backend
    const params = new URLSearchParams({
      limit,
      offset,
      ...(cameraId && { camera_id: cameraId })
    });

    const response = await fetch(`${backendUrl}/api/video/detections?${params.toString()}`);
    
    if (!response.ok) {
      throw new Error(`Backend error: ${response.status}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
    
  } catch (error) {
    console.error("Error fetching detections:", error);
    return NextResponse.json(
      { error: "Failed to fetch detections" },
      { status: 500 }
    );
  }
}
