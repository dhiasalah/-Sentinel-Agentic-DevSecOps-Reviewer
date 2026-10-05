import type { NextRequest } from "next/server";

import { getViewer } from "@/lib/auth";
import { openScanFeed, parseId } from "@/lib/data";

// Server-Sent Events: one long HTTP response the server keeps writing to, read in the browser by EventSource.
// The worker never talks to the browser. It writes rows to the database; this route reads them as the
// signed-in user (row-level security applies) and forwards the new ones.

export const maxDuration = 60;

const POLL_MS = 1500;
// Close before the platform's time limit; EventSource reconnects by itself and sends Last-Event-ID.
const STREAM_MS = 50_000;

const HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  "X-Accel-Buffering": "no",
};

function lastEventId(request: NextRequest): number {
  const raw = request.headers.get("last-event-id") ?? "";
  return /^[0-9]{1,15}$/.test(raw) ? Number(raw) : 0;
}

function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => (clearTimeout(timer), resolve()), { once: true });
  });
}

export async function GET(request: NextRequest, { params }: RouteContext<"/dashboard/scans/[id]/events">) {
  if (!(await getViewer())) return new Response("Sign in first.\n", { status: 401 });
  const id = parseId((await params).id);
  const feed = id ? await openScanFeed(id) : null;
  if (!feed || !(await feed.status())) return new Response("Not found.\n", { status: 404 });

  const signal = request.signal;
  let lastId = lastEventId(request);
  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (text: string) => controller.enqueue(encoder.encode(text));
      const deadline = Date.now() + STREAM_MS;
      send("retry: 2000\n\n");
      try {
        while (!signal.aborted && Date.now() < deadline) {
          const status = await feed.status();
          for (const event of await feed.eventsAfter(lastId)) {
            send(`id: ${event.id}\nevent: progress\ndata: ${JSON.stringify(event)}\n\n`);
            lastId = event.id;
          }
          if (status !== "running") {
            send(`event: end\ndata: ${JSON.stringify({ status })}\n\n`);
            break;
          }
          send(": still running\n\n");
          await sleep(POLL_MS, signal);
        }
      } catch {
        // Database hiccup: end this response; the browser reconnects and resumes from Last-Event-ID.
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, { headers: HEADERS });
}
