import { NextResponse } from "next/server";
import { z } from "zod";

import {
  deleteZoneFolder,
  updateZoneFolder,
} from "@/lib/zoneFolders";

export const dynamic = "force-dynamic";

const patchSchema = z.object({
  name: z.string().min(1).max(80).optional(),
  searchKeyword: z.string().max(200).optional(),
  parentId: z.string().nullable().optional(),
  sortOrder: z.number().optional(),
});

export async function PATCH(
  request: Request,
  { params }: { params: { id: string } },
) {
  let body: z.infer<typeof patchSchema>;
  try {
    body = patchSchema.parse(await request.json());
  } catch {
    return NextResponse.json(
      { status: 400, data: null, message: "参数无效" },
      { status: 400 },
    );
  }

  try {
    const { store, folder } = await updateZoneFolder(params.id, body);
    return NextResponse.json({
      status: 200,
      data: { folder, store },
      message: "已保存",
    });
  } catch (err) {
    return NextResponse.json(
      {
        status: 400,
        data: null,
        message: err instanceof Error ? err.message : "更新失败",
      },
      { status: 400 },
    );
  }
}

export async function DELETE(
  _request: Request,
  { params }: { params: { id: string } },
) {
  try {
    const store = await deleteZoneFolder(params.id);
    return NextResponse.json({
      status: 200,
      data: { store },
      message: "已删除",
    });
  } catch (err) {
    return NextResponse.json(
      {
        status: 400,
        data: null,
        message: err instanceof Error ? err.message : "删除失败",
      },
      { status: 400 },
    );
  }
}
