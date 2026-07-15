import { NextResponse } from "next/server";
import { z } from "zod";

import {
  readP115Config,
  toPublicStatus,
  writeP115Config,
} from "@/lib/p115Config";
import { validateP115 } from "@/lib/p115";

export const dynamic = "force-dynamic";

export async function GET() {
  const cfg = await readP115Config();

  return NextResponse.json({
    status: 200,
    data: toPublicStatus(cfg),
    message: "ok",
  });
}

const putSchema = z.object({
  cookie: z.string().optional(),
  folderCid: z.string().optional(),
  folderName: z.string().optional(),
  label: z.string().optional(),
  validate: z.boolean().optional(),
});

export async function PUT(request: Request) {
  let body: z.infer<typeof putSchema>;

  try {
    body = putSchema.parse(await request.json());
  } catch {
    return NextResponse.json(
      { status: 400, data: null, message: "参数无效" },
      { status: 400 },
    );
  }

  const prev = await readP115Config();
  const cookie = body.cookie !== undefined ? body.cookie : prev.cookie;
  const folderCid = body.folderCid !== undefined ? body.folderCid : prev.folderCid;

  let folderName = body.folderName;
  let validateMsg = "";

  if (body.validate !== false && cookie) {
    const check = await validateP115(cookie, folderCid || "0");

    if (!check.ok) {
      return NextResponse.json(
        { status: 400, data: null, message: check.message },
        { status: 400 },
      );
    }
    folderName = folderName ?? check.folderName;
    validateMsg = check.message;

    const saved = await writeP115Config({
      cookie,
      folderCid,
      folderName,
      label: body.label,
    });

    return NextResponse.json({
      status: 200,
      data: {
        ...toPublicStatus(saved),
        quota: check.quota ?? null,
        quotaTotal: check.quotaTotal ?? null,
      },
      message: validateMsg || "已保存",
    });
  }

  const saved = await writeP115Config({
    cookie,
    folderCid,
    folderName,
    label: body.label,
  });

  return NextResponse.json({
    status: 200,
    data: toPublicStatus(saved),
    message: validateMsg || "已保存",
  });
}
