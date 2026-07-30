import { NextRequest, NextResponse } from "next/server";

import { listPrefixCodes } from "@/app/api/graphql/service";

export const dynamic = "force-dynamic";

/** 按厂牌前缀列出库内番号，供刮削表单选择 */
export async function GET(req: NextRequest) {
  try {
    const prefix = (req.nextUrl.searchParams.get("prefix") || "").trim();
    if (!prefix) {
      return NextResponse.json({ message: "缺少 prefix" }, { status: 400 });
    }
    const limit = Number(req.nextUrl.searchParams.get("limit") || "500");
    const offset = Number(req.nextUrl.searchParams.get("offset") || "0");
    const data = await listPrefixCodes(prefix, { limit, offset });
    return NextResponse.json({
      prefix: prefix.toUpperCase(),
      codes: data.codes.map((c) => c.code),
      total: data.total_codes,
    });
  } catch (err) {
    return NextResponse.json(
      { message: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
