import { NextResponse } from "next/server";

import { scrapeFetch } from "@/lib/scrapeClient";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await scrapeFetch("/api/status", {
      signal: AbortSignal.timeout(10000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        message: err instanceof Error ? err.message : String(err),
        queue: { pending: 0, running: 0, done: 0, error: 0 },
        recent: [],
        logs: [],
      },
      { status: 502 },
    );
  }
}
