import { NextResponse } from "next/server";
import { z } from "zod";

import { reorderZoneSiblings } from "@/lib/zoneFolders";

export const dynamic = "force-dynamic";

const schema = z.object({
  parentId: z.string().nullable(),
  orderedIds: z.array(z.string().min(1)).min(1),
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

  try {
    const store = await reorderZoneSiblings(body.parentId, body.orderedIds);
    return NextResponse.json({
      status: 200,
      data: { store },
      message: "已排序",
    });
  } catch (err) {
    return NextResponse.json(
      {
        status: 400,
        data: null,
        message: err instanceof Error ? err.message : "排序失败",
      },
      { status: 400 },
    );
  }
}
