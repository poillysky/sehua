/**
 * 从资源库扫描番号，把缺 av_metadata 封面的入队。
 *
 * 用法（scrape-web 目录）:
 *   npm run backfill -- --limit 200
 *   npm run backfill -- --limit 0 --prefix SSIS
 *   npm run backfill -- --dry-run --limit 50
 */
import { pool, ensureSchema, enqueueCodes, normalizeCode } from "./db.js";

function argValue(name: string): string | undefined {
  const idx = process.argv.indexOf(name);
  if (idx >= 0 && process.argv[idx + 1]) return process.argv[idx + 1];
  return undefined;
}

function hasFlag(name: string): boolean {
  return process.argv.includes(name);
}

/** 粗提取通用有码番号 PREFIX-123 */
function extractCodes(filename: string): string[] {
  const upper = String(filename || "").toUpperCase();
  const out = new Set<string>();
  const re =
    /(?:^|[^A-Z0-9])([A-Z]{2,10})[-_\s]?(\d{2,6})(?![A-Z0-9])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(upper)) !== null) {
    if (m[1] === "FC2") continue;
    const code = normalizeCode(`${m[1]}-${m[2]}`);
    if (code) out.add(code);
  }
  return Array.from(out);
}

async function main() {
  await ensureSchema();
  const limit = Number(argValue("--limit") ?? "200");
  const prefix = (argValue("--prefix") || "").trim().toUpperCase();
  const dryRun = hasFlag("--dry-run");

  const params: unknown[] = [];
  let where = `WHERE COALESCE(r.filename, '') <> ''`;
  if (prefix) {
    params.push(`%${prefix}%`);
    where += ` AND r.filename ILIKE $${params.length}`;
  }

  let limSql = "";
  if (limit > 0) {
    params.push(limit);
    limSql = `LIMIT $${params.length}`;
  }

  const sql = `
SELECT DISTINCT r.filename
FROM ed2k_resources r
${where}
ORDER BY r.filename
${limSql}
`;
  const { rows } = await pool.query<{ filename: string }>(sql, params);
  const codes = new Set<string>();
  for (const row of rows) {
    for (const c of extractCodes(row.filename)) {
      if (prefix && !c.startsWith(`${prefix}-`)) continue;
      codes.add(c);
    }
  }

  const list = Array.from(codes);
  console.log(
    `scanned_files=${rows.length} unique_codes=${list.length} dry_run=${dryRun}`,
  );
  if (dryRun) {
    console.log(list.slice(0, 40).join("\n"));
    if (list.length > 40) console.log(`... +${list.length - 40}`);
    await pool.end();
    return;
  }

  // 只入队库里还没有 ok 封面的
  const { rows: okRows } = await pool.query<{ code: string }>(
    `SELECT code FROM av_metadata
     WHERE status = 'ok' AND coalesce(cover_path, '') <> ''
       AND code = ANY($1)`,
    [list],
  );
  const ok = new Set(okRows.map((r) => r.code));
  const need = list.filter((c) => !ok.has(c));
  console.log(`need_scrape=${need.length} already_ok=${ok.size}`);

  const chunk = 200;
  let enqueued = 0;
  let skipped = 0;
  for (let i = 0; i < need.length; i += chunk) {
    const part = need.slice(i, i + chunk);
    const r = await enqueueCodes(part, 0);
    enqueued += r.enqueued;
    skipped += r.skipped;
    console.log(`enqueued batch ${i / chunk + 1}: +${r.enqueued}`);
  }
  console.log(`done enqueued=${enqueued} skipped=${skipped}`);
  await pool.end();
}

main().catch(async (err) => {
  console.error(err);
  await pool.end().catch(() => undefined);
  process.exit(1);
});
