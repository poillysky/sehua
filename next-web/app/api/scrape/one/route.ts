import { NextRequest, NextResponse } from "next/server";

import { scrapeFetch } from "@/lib/scrapeClient";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as {
      code?: string;
      sync?: boolean;
      overwrite?: boolean;
      kind?: string;
    };
    const code = String(body.code || "").trim();
    if (!code) {
      return NextResponse.json({ message: "缺少番号 code" }, { status: 400 });
    }
    const sync = Boolean(body.sync);
    const overwrite = body.overwrite !== false;
    const qs = new URLSearchParams();
    if (sync) qs.set("sync", "1");
    if (overwrite) qs.set("overwrite", "1");
    const q = qs.toString();
    const path = `/api/scrape/${encodeURIComponent(code)}${q ? `?${q}` : ""}`;
    const res = await scrapeFetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        overwrite,
        ...(body.kind ? { kind: body.kind } : {}),
      }),
      signal: AbortSignal.timeout(sync ? 90000 : 15000),
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
