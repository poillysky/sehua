import { NextResponse } from "next/server";

import { fetchUpstreamImage } from "@/lib/fetchUpstreamImage";
import { isAllowedImageUrl } from "@/lib/imageProxy";

export const dynamic = "force-dynamic";

type CacheHit = { buffer: Buffer; contentType: string; expires: number };
const memCache = new Map<string, CacheHit>();
const MEM_TTL_MS = 30 * 60 * 1000;
const MEM_MAX = 200;

function getCached(url: string): CacheHit | null {
  const hit = memCache.get(url);
  if (!hit) return null;
  if (hit.expires <= Date.now()) {
    memCache.delete(url);
    return null;
  }
  return hit;
}

function setCached(url: string, buffer: Buffer, contentType: string) {
  if (memCache.size >= MEM_MAX) {
    const oldest = memCache.keys().next().value;
    if (oldest) memCache.delete(oldest);
  }
  memCache.set(url, {
    buffer,
    contentType,
    expires: Date.now() + MEM_TTL_MS,
  });
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const targetUrl = searchParams.get("url");

  if (!targetUrl || !isAllowedImageUrl(targetUrl)) {
    return NextResponse.json({ message: "Invalid image url" }, { status: 400 });
  }

  const cached = getCached(targetUrl);
  if (cached) {
    return new NextResponse(cached.buffer, {
      status: 200,
      headers: {
        "Content-Type": cached.contentType,
        "Cache-Control": "public, max-age=604800, stale-while-revalidate=86400",
        "X-Image-Cache": "HIT",
      },
    });
  }

  try {
    const { buffer, contentType } = await fetchUpstreamImage(targetUrl);
    setCached(targetUrl, buffer, contentType);

    return new NextResponse(buffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "public, max-age=604800, stale-while-revalidate=86400",
        "X-Image-Cache": "MISS",
      },
    });
  } catch (error: any) {
    const message = error?.message || "Image proxy failed";
    console.error("[image-proxy] fetch failed", targetUrl, message);
    return NextResponse.json({ message }, { status: 502 });
  }
}
