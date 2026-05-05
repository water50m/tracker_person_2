import { NextRequest, NextResponse } from "next/server";

/**
 * GET /api/search/results
 *
 * Query params:
 *   - clothing[]       : array of clothing types (Shirt, Jacket, ...)
 *   - colors[]         : array of colors (Red, Black, ...)
 *   - logic            : "OR" | "AND"  (default: "OR")
 *   - threshold        : number 0-1   (color similarity threshold)
 *   - camera_id        : string (optional)
 *   - start_time       : ISO date string (optional)
 *   - end_time         : ISO date string (optional)
 *   - page             : number (default: 1)
 *   - limit            : number (default: 24)
 *   // New color system filters
 *   - tone_groups[]    : array of tone groups (red_tones, blue_tones, ...)
 *   - temperature      : "warm" | "cool" | "neutral"
 *   - brightness       : "light" | "dark" | "medium"
 *   - vibrancy         : "vibrant" | "muted" | "pastel"
 *   - clothing_groups[]: array of clothing color groups (common_shirt_colors, formal_colors, ...)
 *
 * Returns: { results: SearchResult[], total: number, page: number, has_more: boolean }
 */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;

  const clothing = searchParams.getAll("clothing[]");
  const colors = searchParams.getAll("colors[]");
  const logic = searchParams.get("logic") ?? "OR";
  const threshold = parseFloat(searchParams.get("threshold") ?? "0.7");
  const cameraId = searchParams.get("camera_id");
  const videoId = searchParams.get("video_id");
  const startTime = searchParams.get("start_time");
  const endTime = searchParams.get("end_time");
  const page = parseInt(searchParams.get("page") ?? "1");
  const limit = Math.min(parseInt(searchParams.get("limit") ?? "24"), 100);

  // New color system filters
  const toneGroups = searchParams.getAll("tone_groups[]");
  const temperature = searchParams.get("temperature");
  const brightness = searchParams.get("brightness");
  const vibrancy = searchParams.get("vibrancy");
  const clothingGroups = searchParams.getAll("clothing_groups[]");

  // Require at least one filter — unless scoped by camera or video
  const hasClothingOrColor = clothing.filter(Boolean).length > 0 || colors.length > 0;
  const hasColorFilters = toneGroups.length > 0 || !!temperature || !!brightness || !!vibrancy || clothingGroups.length > 0;
  const hasScopeFilter = !!cameraId || !!videoId;
  if (!hasClothingOrColor && !hasScopeFilter && !hasColorFilters) {
    return NextResponse.json(
      { error: "At least one clothing type, color, camera, or video is required" },
      { status: 400 }
    );
  }

  if (!["OR", "AND"].includes(logic)) {
    return NextResponse.json(
      { error: "Logic must be OR or AND" },
      { status: 400 }
    );
  }

  try {
    const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

    // Build backend query
    const backendParams = new URLSearchParams();
    clothing.forEach((c) => backendParams.append("clothing[]", c));
    colors.forEach((c) => backendParams.append("colors[]", c));
    backendParams.set("logic", logic);
    backendParams.set("threshold", threshold.toString());
    if (cameraId) backendParams.set("camera_id", cameraId);
    if (videoId) backendParams.set("video_id", videoId);
    if (startTime) backendParams.set("start_time", startTime);
    if (endTime) backendParams.set("end_time", endTime);
    backendParams.set("page", page.toString());
    backendParams.set("limit", limit.toString());

    // New color system filters
    toneGroups.forEach((g) => backendParams.append("tone_groups[]", g));
    if (temperature) backendParams.set("temperature", temperature);
    if (brightness) backendParams.set("brightness", brightness);
    if (vibrancy) backendParams.set("vibrancy", vibrancy);
    clothingGroups.forEach((g) => backendParams.append("clothing_groups[]", g));

    const backendRes = await fetch(
      `${backendUrl}/api/search/persons?${backendParams.toString()}`,
      { next: { revalidate: 0 } } // Always fresh
    );

    if (!backendRes.ok) {
      throw new Error(`Backend responded with ${backendRes.status}`);
    }

    const data = await backendRes.json();

    return NextResponse.json({
      results: data.results ?? [],
      total: data.total ?? 0,
      page: data.page ?? page,
      has_more: data.has_more ?? false,
    });
  } catch (err) {
    console.error("[search/results] Error:", err);
    return NextResponse.json(
      { error: "Failed to fetch search results" },
      { status: 500 }
    );
  }
}
