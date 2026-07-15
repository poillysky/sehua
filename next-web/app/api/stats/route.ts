import { NextResponse } from "next/server";

import { statsInfo } from "@/app/api/graphql/service";

const handler = async () => {
  try {
    const data = await statsInfo();

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
          "Cache-Control": "public, s-maxage=60, stale-while-revalidate=120",
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
