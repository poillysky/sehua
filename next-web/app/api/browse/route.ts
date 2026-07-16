import { NextResponse } from "next/server";
import { z } from "zod";

import { browseResources } from "@/app/api/graphql/service";
import { BROWSE_PAGE_MAX, BROWSE_PAGE_SIZE } from "@/config/constant";

export const dynamic = "force-dynamic";

const schema = z.object({
  p: z.coerce.number().min(1).max(BROWSE_PAGE_MAX).default(1),
  ps: z.coerce.number().min(1).max(50).default(BROWSE_PAGE_SIZE),
});

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const params = Object.fromEntries(searchParams.entries());

  try {
    const { p, ps } = schema.parse(params);
    const offset = (p - 1) * ps;
    const data = await browseResources(null, { limit: ps, offset });

    return NextResponse.json(
      {
        data: data.resources,
        total_count: data.total_count,
        page: p,
        page_size: ps,
        message: "success",
        status: 200,
      },
      {
        status: 200,
        headers: { "Cache-Control": "no-store" },
      },
    );
  } catch (error: any) {
    console.error(error);

    return NextResponse.json(
      {
        data: [],
        total_count: 0,
        page: 1,
        page_size: BROWSE_PAGE_SIZE,
        message: error?.message || "Internal Server Error",
        status: 500,
      },
      { status: 500 },
    );
  }
}
