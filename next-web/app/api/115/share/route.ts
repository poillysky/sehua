import { NextResponse } from "next/server";
import { z } from "zod";

import { readP115Config } from "@/lib/p115Config";
import { is115ShareLink, receive115Shares } from "@/lib/p115Share";

export const dynamic = "force-dynamic";

const schema = z.object({
  urls: z.array(z.string()).min(1).max(20),
  folderCid: z.string().optional(),
  /** 访问码兜底（链接未带 password 时） */
  password: z.string().optional(),
});

export async function POST(request: Request) {
  let body: z.infer<typeof schema>;

  try {
    body = schema.parse(await request.json());
  } catch {
    return NextResponse.json(
      { status: 400, data: null, message: "参数无效" },
      { status: 400 },
    );
  }

  const cfg = await readP115Config();

  if (!cfg.cookie) {
    return NextResponse.json(
      {
        status: 400,
        data: null,
        message: "尚未配置 115，请先打开「115设置」填写 Cookie",
      },
      { status: 400 },
    );
  }

  const urls = body.urls.filter((u) => is115ShareLink(u));

  if (!urls.length) {
    return NextResponse.json(
      { status: 400, data: null, message: "没有可转存的 115 分享链接" },
      { status: 400 },
    );
  }

  const folderCid = body.folderCid || cfg.folderCid || "0";
  const result = await receive115Shares(
    cfg.cookie,
    urls,
    folderCid,
    (body.password || "").trim(),
  );

  return NextResponse.json(
    {
      status: result.ok ? 200 : 400,
      data: result,
      message: result.message,
    },
    { status: result.ok ? 200 : 400 },
  );
}
