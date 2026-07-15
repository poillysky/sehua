import { NextResponse } from "next/server";
import { z } from "zod";

import { listFolders } from "@/lib/p115";
import { readP115Config } from "@/lib/p115Config";

export const dynamic = "force-dynamic";

const schema = z.object({
  cid: z.string().optional(),
  cookie: z.string().optional(),
});

async function resolve(body: z.infer<typeof schema>) {
  const cfg = await readP115Config();
  const cookie = (body.cookie || cfg.cookie || "").trim();

  if (!cookie) {
    return NextResponse.json(
      { status: 400, data: null, message: "请先配置 115 Cookie" },
      { status: 400 },
    );
  }

  const result = await listFolders(cookie, body.cid || "0");

  return NextResponse.json(
    {
      status: result.ok ? 200 : 400,
      data: result,
      message: result.message,
    },
    { status: result.ok ? 200 : 400 },
  );
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const parsed = schema.safeParse({
    cid: searchParams.get("cid") || undefined,
  });

  if (!parsed.success) {
    return NextResponse.json(
      { status: 400, data: null, message: "参数无效" },
      { status: 400 },
    );
  }

  return resolve(parsed.data);
}

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

  return resolve(body);
}
