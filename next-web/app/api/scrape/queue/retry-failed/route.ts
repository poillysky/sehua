import { NextResponse } from "next/server";

import { scrapeFetch } from "@/lib/scrapeClient";

export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const res = await scrapeFetch("/api/queue/retry-failed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(30000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { message: err instanceof Error ? err.message : String(err) },
      { status: 502 },
    );
  }
}
