import { NextRequest } from "next/server";

/**
 * GET /api/events/live
 *
 * Server-Sent Events (SSE) stream for real-time event feed on the dashboard.
 * Proxies from the AI backend's event stream.
 *
 * Event format:
 *   data: { type: "detection", payload: DetectionEvent }
 *   data: { type: "stats_update", payload: StatsPayload }
 *   data: { type: "heartbeat" }
 */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const cameraIds = searchParams.getAll("camera_id[]");

  const encoder = new TextEncoder();
  const backendUrl = process.env.AI_BACKEND_URL ?? "http://localhost:8000";

  const stream = new ReadableStream({
    async start(controller) {
      const sendEvent = (data: object) => {
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify(data)}\n\n`)
        );
      };

      // Try to proxy from real backend SSE
      try {
        const params = new URLSearchParams();
        cameraIds.forEach((id) => params.append("camera_id[]", id));

        const backendRes = await fetch(
          `${backendUrl}/api/events/stream?${params.toString()}`,
          {
            headers: { Accept: "text/event-stream" },
            signal: request.signal,
          }
        );

        if (!backendRes.ok || !backendRes.body) {
          throw new Error("Backend SSE unavailable");
        }

        const reader = backendRes.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop() ?? "";

          for (const chunk of lines) {
            if (chunk.startsWith("data: ")) {
              controller.enqueue(encoder.encode(chunk + "\n\n"));
            }
          }
        }
      } catch {
        // Backend unavailable - send mock events for development
        console.warn("[events/live] Backend unavailable, using mock events");

        const mockCameras = ["CAM-01", "CAM-02", "CAM-03", "CAM-04"];
        const mockClothing = ["Red Shirt", "Black Jacket", "Blue Jeans", "White T-Shirt", "Dark Hoodie"];
        let eventId = 1000;

        const interval = setInterval(() => {
          if (request.signal.aborted) {
            clearInterval(interval);
            controller.close();
            return;
          }

          // Random detection event
          if (Math.random() > 0.3) {
            sendEvent({
              type: "detection",
              payload: {
                id: `evt-${eventId++}`,
                camera_id: mockCameras[Math.floor(Math.random() * mockCameras.length)],
                timestamp: new Date().toISOString(),
                clothing: mockClothing[Math.floor(Math.random() * mockClothing.length)],
                confidence: Math.round((0.75 + Math.random() * 0.24) * 100) / 100,
                thumbnail_url: `https://picsum.photos/seed/${eventId}/80/120`,
              },
            });
          }

          // Stats update every 10 events
          if (eventId % 10 === 0) {
            sendEvent({
              type: "stats_update",
              payload: {
                total_today: 247 + Math.floor(Math.random() * 5),
                active_cameras: 4,
                detections_per_hour: Math.floor(30 + Math.random() * 20),
              },
            });
          }
        }, 2000);

        // Heartbeat
        const heartbeat = setInterval(() => {
          if (request.signal.aborted) {
            clearInterval(heartbeat);
            return;
          }
          sendEvent({ type: "heartbeat", ts: Date.now() });
        }, 15000);

        request.signal.addEventListener("abort", () => {
          clearInterval(interval);
          clearInterval(heartbeat);
          controller.close();
        });
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no", // Nginx: disable buffering
    },
  });
}
