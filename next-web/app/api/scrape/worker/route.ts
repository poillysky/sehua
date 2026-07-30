import { NextRequest, NextResponse } from "next/server";

import { scrapeFetch } from "@/lib/scrapeClient";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const action = (req.nextUrl.searchParams.get("action") || "").trim();
    if (action === "stop") {
      const res = await scrapeFetch("/api/worker/stop", {
        method: "POST",
        signal: AbortSignal.timeout(15000),
      });
      const data = await res.json().catch(() => ({}));
      return NextResponse.json(data, { status: res.status });
    }
    if (action === "start") {
      const res = await scrapeFetch("/api/worker/start", {
        method: "POST",
        signal: AbortSignal.timeout(15000),
      });
      const data = await res.json().catch(() => ({}));
      return NextResponse.json(data, { status: res.status });
    }
    return NextResponse.json(
      { message: "action 需为 start 或 stop" },
      { status: 400 },
    );
  } catch (err) {
    return NextResponse.json(
      { message: err instanceof Error ? err.message : String(err) },
      { status: 502 },
    );
  }
}
