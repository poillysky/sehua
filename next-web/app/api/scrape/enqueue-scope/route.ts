import { NextRequest, NextResponse } from "next/server";

import { listPrefixCodes } from "@/app/api/graphql/service";
import {
  resolveScopePrefixes,
  type ScrapeAutoScope,
  type ScrapeRegionId,
} from "@/config/boards";
import { scrapeFetch } from "@/lib/scrapeClient";

export const dynamic = "force-dynamic";

const CHUNK = 200;

function asRegion(v: unknown): ScrapeRegionId {
  const s = String(v || "").trim();
  if (s === "国产" || s === "欧美" || s === "手动" || s === "日本") return s;
  return "日本";
}

/** 按多级板块解析番号并入队（顺序：厂牌字母序 × 番号序） */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const scope: ScrapeAutoScope = {
      region: asRegion(body.region),
      board: String(body.board || "").trim(),
      prefix: String(body.prefix || "")
        .trim()
        .toUpperCase(),
      code: String(body.code || "")
        .trim()
        .toUpperCase(),
    };
    const overwrite = Boolean(body.overwrite);

    if (scope.code) {
      const res = await scrapeFetch("/api/scrape/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ codes: [scope.code], overwrite }),
        signal: AbortSignal.timeout(60000),
      });
      const data = await res.json().catch(() => ({}));
      return NextResponse.json(
        {
          ...data,
          scope,
          codes: 1,
          prefixes: scope.prefix ? [scope.prefix] : [],
        },
        { status: res.status },
      );
    }

    const prefixes = resolveScopePrefixes(scope);
    if (!prefixes.length) {
      return NextResponse.json(
        { message: "该板块下没有可刮削的厂牌", scope },
        { status: 400 },
      );
    }

    const allCodes: string[] = [];
    const seen = new Set<string>();
    for (const p of prefixes) {
      const data = await listPrefixCodes(p.prefix, { limit: 2000, offset: 0 });
      for (const hit of data.codes) {
        const c = String(hit.code || "")
          .trim()
          .toUpperCase();
        if (!c || seen.has(c)) continue;
        seen.add(c);
        allCodes.push(c);
      }
    }

    if (!allCodes.length) {
      return NextResponse.json(
        {
          message: "该板块下库内暂无番号",
          scope,
          prefixes: prefixes.map((p) => p.prefix),
          enqueued: 0,
          skipped: 0,
        },
        { status: 200 },
      );
    }

    let enqueued = 0;
    let skipped = 0;
    for (let i = 0; i < allCodes.length; i += CHUNK) {
      const chunk = allCodes.slice(i, i + CHUNK);
      const res = await scrapeFetch("/api/scrape/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ codes: chunk, overwrite }),
        signal: AbortSignal.timeout(120000),
      });
      const data = (await res.json().catch(() => ({}))) as {
        enqueued?: number;
        skipped?: number;
        message?: string;
      };
      if (!res.ok) {
        return NextResponse.json(
          {
            message: data.message || "入队失败",
            scope,
            partial: { enqueued, skipped, at: i },
          },
          { status: res.status },
        );
      }
      enqueued += Number(data.enqueued || 0);
      skipped += Number(data.skipped || 0);
    }

    return NextResponse.json({
      ok: true,
      scope,
      prefixes: prefixes.map((p) => p.prefix),
      codes: allCodes.length,
      enqueued,
      skipped,
      overwrite,
    });
  } catch (err) {
    return NextResponse.json(
      { message: err instanceof Error ? err.message : String(err) },
      { status: 502 },
    );
  }
}
