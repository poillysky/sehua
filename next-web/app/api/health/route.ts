import { NextResponse } from "next/server";

import { query } from "@/lib/pgdb";

export async function GET() {
  try {
    const [{ rows: pingRows }, { rows: extRows }] = await Promise.all([
      query("SELECT COUNT(*)::int AS total FROM ed2k_resources"),
      query(
        "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') AS enabled",
      ),
    ]);

    return NextResponse.json({
      status: "ok",
      db: true,
      total_resources: pingRows[0]?.total ?? 0,
      pg_trgm: Boolean(extRows[0]?.enabled),
      timestamp: new Date().toISOString(),
    });
  } catch (error: any) {
    return NextResponse.json(
      {
        status: "error",
        db: false,
        message: error?.message || "Database unavailable",
        timestamp: new Date().toISOString(),
      },
      { status: 503 },
    );
  }
}
