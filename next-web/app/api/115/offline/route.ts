import { NextResponse } from "next/server";
import { z } from "zod";

import { addOfflineTasks } from "@/lib/p115";
import { scheduleDeferredExtract } from "@/lib/p115Extract";
import { readP115Config } from "@/lib/p115Config";
import { isPublicDownloadLink } from "@/utils/resource";

export const dynamic = "force-dynamic";

const schema = z.object({
  urls: z.array(z.string()).min(1).max(50),
  folderCid: z.string().optional(),
  /** 资源解压密码；有值则转存后轮询，完成后立即云解压 */
  password: z.string().optional(),
  titleHint: z.string().optional(),
  /** 默认：有密码则自动安排解压 */
  autoExtract: z.boolean().optional(),
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

  const urls = body.urls.filter((u) => isPublicDownloadLink(u));

  if (!urls.length) {
    return NextResponse.json(
      { status: 400, data: null, message: "没有可转存的磁力/ED2K 链接" },
      { status: 400 },
    );
  }

  const folderCid = body.folderCid || cfg.folderCid || "0";
  const result = await addOfflineTasks(cfg.cookie, urls, folderCid);
  const password = (body.password || "").trim();
  const wantExtract =
    result.ok &&
    result.added > 0 &&
    Boolean(password) &&
    body.autoExtract !== false;

  let extractScheduled = false;

  if (wantExtract) {
    scheduleDeferredExtract({
      cookie: cfg.cookie,
      folderCid,
      password,
      infoHashes: result.infoHashes || [],
      titleHint: body.titleHint || "",
    });
    extractScheduled = true;
  }

  const message = extractScheduled
    ? `${result.message} · 后台轮询转存（最长约 30 秒），完成后立即云解压`
    : result.message;

  return NextResponse.json(
    {
      status: result.ok ? 200 : 400,
      data: {
        ...result,
        extractScheduled,
        extractMode: extractScheduled ? "poll" : null,
      },
      message,
    },
    { status: result.ok ? 200 : 400 },
  );
}
