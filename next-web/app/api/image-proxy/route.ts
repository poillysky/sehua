import { NextResponse } from "next/server";

import { fetchUpstreamImage } from "@/lib/fetchUpstreamImage";
import { isAllowedImageUrl } from "@/lib/imageProxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const targetUrl = searchParams.get("url");

  if (!targetUrl || !isAllowedImageUrl(targetUrl)) {
    return NextResponse.json({ message: "Invalid image url" }, { status: 400 });
  }

  try {
    const { buffer, contentType } = await fetchUpstreamImage(targetUrl);

    return new NextResponse(buffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "public, max-age=604800, stale-while-revalidate=86400",
      },
    });
  } catch (error: any) {
    const message = error?.message || "Image proxy failed";
    console.error("[image-proxy] fetch failed", targetUrl, message);
    return NextResponse.json({ message }, { status: 502 });
  }
}
