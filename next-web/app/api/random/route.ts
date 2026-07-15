import { NextResponse } from "next/server";
import { z } from "zod";

import { randomResources } from "@/app/api/graphql/service";

const schema = z.object({
  limit: z.coerce.number().min(1).max(50).default(15),
});

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const params = Object.fromEntries(searchParams.entries());

  try {
    const { limit } = schema.parse(params);
    const data = await randomResources(null, { limit });

    return NextResponse.json(
      {
        data,
        message: "success",
        status: 200,
      },
      {
        status: 200,
        headers: {
          "Cache-Control": "no-store",
        },
      },
    );
  } catch (error: any) {
    console.error(error);

    return NextResponse.json(
      {
        data: [],
        message: error?.message || "Internal Server Error",
        status: 500,
      },
      { status: 500 },
    );
  }
}
