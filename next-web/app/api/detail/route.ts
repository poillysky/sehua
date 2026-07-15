import { NextResponse } from "next/server";

import { resourceByHash } from "@/app/api/graphql/service";

const handler = async (request: Request) => {
  const { searchParams } = new URL(request.url);
  const hash = searchParams.get("hash");

  if (!hash) {
    return NextResponse.json(
      {
        message: "`hash` is required",
        status: 400,
      },
      {
        status: 400,
      },
    );
  }

  try {
    const data = await resourceByHash(null, { hash });

    return NextResponse.json(
      {
        data,
        message: "success",
        status: 200,
      },
      {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "no-store",
        },
      },
    );
  } catch (error: any) {
    console.error(error);

    return NextResponse.json(
      {
        message: error?.message || "Internal Server Error",
        status: 500,
      },
      {
        status: 500,
      },
    );
  }
};

export { handler as GET, handler as POST };
