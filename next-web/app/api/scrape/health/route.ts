import { NextResponse } from "next/server";

import { scrapeFetch } from "@/lib/scrapeClient";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await scrapeFetch("/health", {
      signal: AbortSignal.timeout(5000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(
      {
        ok: res.ok && Boolean(data?.ok),
        status: res.status,
        data,
        origin: process.env.SCRAPE_ORIGIN || "http://127.0.0.1:9209",
      },
      { status: res.ok ? 200 : 502 },
    );
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        status: 0,
        data: null,
        message: err instanceof Error ? err.message : String(err),
        origin: process.env.SCRAPE_ORIGIN || "http://127.0.0.1:9209",
      },
      { status: 502 },
    );
  }
}
