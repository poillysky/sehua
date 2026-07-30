import { NextResponse } from "next/server";
import { z } from "zod";

import {
  createZoneFolder,
  importZoneFolders,
  readZoneFolders,
} from "@/lib/zoneFolders";

export const dynamic = "force-dynamic";

export async function GET() {
  const store = await readZoneFolders();
  return NextResponse.json({
    status: 200,
    data: store,
    message: "ok",
  });
}

const postSchema = z.object({
  name: z.string().min(1).max(80),
  parentId: z.string().nullable().optional(),
  kind: z.enum(["folder", "search"]).optional(),
  searchKeyword: z.string().max(200).optional(),
});

export async function POST(request: Request) {
  let body: z.infer<typeof postSchema>;
  try {
    body = postSchema.parse(await request.json());
  } catch {
    return NextResponse.json(
      { status: 400, data: null, message: "参数无效" },
      { status: 400 },
    );
  }

  try {
    const { store, folder } = await createZoneFolder({
      name: body.name,
      parentId: body.parentId ?? null,
      kind: body.kind,
      searchKeyword: body.searchKeyword,
    });
    return NextResponse.json({
      status: 200,
      data: { folder, store },
      message: "已创建",
    });
  } catch (err) {
    return NextResponse.json(
      {
        status: 400,
        data: null,
        message: err instanceof Error ? err.message : "创建失败",
      },
      { status: 400 },
    );
  }
}

const putSchema = z.object({
  folders: z.array(z.unknown()),
});

/** 整树导入（覆盖） */
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

  try {
    const store = await importZoneFolders(body.folders);
    return NextResponse.json({
      status: 200,
      data: store,
      message: `已导入 ${store.folders.length} 项`,
    });
  } catch (err) {
    return NextResponse.json(
      {
        status: 400,
        data: null,
        message: err instanceof Error ? err.message : "导入失败",
      },
      { status: 400 },
    );
  }
}
