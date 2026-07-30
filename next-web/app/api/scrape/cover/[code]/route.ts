import { NextRequest, NextResponse } from "next/server";

import { scrapeFetch } from "@/lib/scrapeClient";

export const dynamic = "force-dynamic";

/**
 * 代理 scrape-web 本地封面。
 * GET /api/scrape/cover/SSIS-001
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { code: string } },
) {
  try {
    const code = String(params.code || "")
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9_-]+/g, "_");
    if (!code) {
      return NextResponse.json({ message: "缺少番号" }, { status: 400 });
    }
    const res = await scrapeFetch(`/covers/${encodeURIComponent(code)}.jpg`, {
      method: "GET",
      signal: AbortSignal.timeout(20000),
    });
    if (!res.ok || !res.body) {
      return NextResponse.json(
        { message: `封面不存在 (${res.status})` },
        { status: res.status === 404 ? 404 : 502 },
      );
    }

    // 透传二进制流，避免 Buffer 序列化问题
    const headers = new Headers();
    headers.set(
      "Content-Type",
      res.headers.get("content-type") || "image/jpeg",
    );
    // 带 ?v= 时禁止长缓存，便于覆盖刮削后立刻看到新图
    const hasBust = Boolean(_req.nextUrl.searchParams.get("v"));
    headers.set(
      "Cache-Control",
      hasBust
        ? "no-store, max-age=0"
        : "public, max-age=86400, immutable",
    );
    const len = res.headers.get("content-length");
    if (len) headers.set("Content-Length", len);

    return new NextResponse(res.body, { status: 200, headers });
  } catch (err) {
    return NextResponse.json(
      { message: err instanceof Error ? err.message : String(err) },
      { status: 502 },
    );
  }
}
