import { NextRequest, NextResponse } from "next/server";

import { scrapeFetch } from "@/lib/scrapeClient";

export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  { params }: { params: { code: string } },
) {
  try {
    const code = String(params.code || "").trim();
    if (!code) {
      return NextResponse.json({ message: "缺少番号" }, { status: 400 });
    }
    const res = await scrapeFetch(`/api/meta/${encodeURIComponent(code)}`, {
      method: "GET",
      signal: AbortSignal.timeout(15000),
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
