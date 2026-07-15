import { NextResponse } from "next/server";
import { z } from "zod";

import { validateP115 } from "@/lib/p115";
import { readP115Config } from "@/lib/p115Config";

export const dynamic = "force-dynamic";

const schema = z.object({
  cookie: z.string().optional(),
  folderCid: z.string().optional(),
});

export async function POST(request: Request) {
  let body: z.infer<typeof schema>;

  try {
    body = schema.parse(await request.json().catch(() => ({})));
  } catch {
    return NextResponse.json(
      { status: 400, data: null, message: "参数无效" },
      { status: 400 },
    );
  }

  const cfg = await readP115Config();
  const cookie = (body.cookie || cfg.cookie || "").trim();
  const folderCid = (body.folderCid || cfg.folderCid || "0").trim();

  if (!cookie) {
    return NextResponse.json(
      { status: 400, data: null, message: "请先填写 115 Cookie" },
      { status: 400 },
    );
  }

  const result = await validateP115(cookie, folderCid);

  return NextResponse.json(
    {
      status: result.ok ? 200 : 400,
      data: result,
      message: result.message,
    },
    { status: result.ok ? 200 : 400 },
  );
}
