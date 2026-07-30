import { config as loadEnv } from "dotenv";
import { Pool } from "pg";

import { hasLocalCover } from "./covers.js";

loadEnv();

function buildConnectionString(): string {
  if (process.env.POSTGRES_DB_URL) {
    return process.env.POSTGRES_DB_URL;
  }
  const host = process.env.POSTGRES_HOST || "127.0.0.1";
  const port = process.env.POSTGRES_PORT || "5435";
  const user = process.env.POSTGRES_USER || "postgres";
  const password = process.env.POSTGRES_PASSWORD || "postgres";
  const db = process.env.POSTGRES_DB || "ed2k";
  return `postgres://${encodeURIComponent(user)}:${encodeURIComponent(password)}@${host}:${port}/${db}`;
}

export const pool = new Pool({
  connectionString: buildConnectionString(),
  max: Number(process.env.PG_POOL_MAX || 8),
});

export async function ensureSchema(): Promise<void> {
  await pool.query(`
CREATE TABLE IF NOT EXISTS av_metadata (
  code TEXT PRIMARY KEY,
  title TEXT,
  title_zh TEXT,
  title_ja TEXT,
  actresses TEXT[],
  cover_path TEXT,
  cover_source TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  error TEXT,
  scraped_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE av_metadata ADD COLUMN IF NOT EXISTS title_zh TEXT;
ALTER TABLE av_metadata ADD COLUMN IF NOT EXISTS title_ja TEXT;
ALTER TABLE av_metadata ADD COLUMN IF NOT EXISTS actresses TEXT[];
CREATE INDEX IF NOT EXISTS idx_av_metadata_status_updated
  ON av_metadata (status, updated_at);
CREATE INDEX IF NOT EXISTS idx_av_metadata_actresses_gin
  ON av_metadata USING GIN (actresses);

CREATE TABLE IF NOT EXISTS av_scrape_queue (
  id BIGSERIAL PRIMARY KEY,
  code TEXT NOT NULL,
  priority INT NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_av_scrape_queue_pending_code
  ON av_scrape_queue (code)
  WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_av_scrape_queue_pick
  ON av_scrape_queue (status, priority DESC, id ASC);
ALTER TABLE av_scrape_queue ADD COLUMN IF NOT EXISTS scrape_mode TEXT;
ALTER TABLE av_scrape_queue ADD COLUMN IF NOT EXISTS force_overwrite BOOLEAN NOT NULL DEFAULT false;
`);
}

export type AvMetaRow = {
  code: string;
  title: string | null;
  title_zh: string | null;
  title_ja: string | null;
  actresses: string[] | null;
  cover_path: string | null;
  cover_source: string | null;
  status: string;
  error: string | null;
  scraped_at: Date | null;
  updated_at: Date;
};

export async function getMeta(code: string): Promise<AvMetaRow | null> {
  const { rows } = await pool.query<AvMetaRow>(
    `SELECT code, title, title_zh, title_ja, actresses, cover_path, cover_source,
            status, error, scraped_at, updated_at
     FROM av_metadata WHERE code = $1`,
    [code],
  );
  return rows[0] || null;
}

export async function upsertMeta(
  row: {
    code: string;
    title?: string | null;
    title_zh?: string | null;
    title_ja?: string | null;
    actresses?: string[] | null;
    cover_path?: string | null;
    cover_source?: string | null;
    status: string;
    error?: string | null;
  },
  opts?: { overwrite?: boolean },
): Promise<void> {
  const overwrite = Boolean(opts?.overwrite);
  if (overwrite && row.status === "ok") {
    await pool.query(
      `INSERT INTO av_metadata (
         code, title, title_zh, title_ja, actresses,
         cover_path, cover_source, status, error, scraped_at, updated_at
       )
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
       ON CONFLICT (code) DO UPDATE SET
         title = COALESCE(EXCLUDED.title, av_metadata.title),
         title_zh = COALESCE(EXCLUDED.title_zh, av_metadata.title_zh),
         title_ja = EXCLUDED.title_ja,
         actresses = CASE
           WHEN EXCLUDED.actresses IS NOT NULL AND cardinality(EXCLUDED.actresses) > 0
             THEN EXCLUDED.actresses
           WHEN EXCLUDED.actresses IS NOT NULL AND cardinality(EXCLUDED.actresses) = 0
             THEN '{}'
           ELSE av_metadata.actresses
         END,
         cover_path = COALESCE(EXCLUDED.cover_path, av_metadata.cover_path),
         cover_source = COALESCE(EXCLUDED.cover_source, av_metadata.cover_source),
         status = EXCLUDED.status,
         error = EXCLUDED.error,
         scraped_at = NOW(),
         updated_at = NOW()`,
      [
        row.code,
        row.title ?? null,
        row.title_zh ?? null,
        row.title_ja ?? null,
        row.actresses ?? null,
        row.cover_path ?? null,
        row.cover_source ?? null,
        row.status,
        row.error ?? null,
      ],
    );
    return;
  }

  await pool.query(
    `INSERT INTO av_metadata (
       code, title, title_zh, title_ja, actresses,
       cover_path, cover_source, status, error, scraped_at, updated_at
     )
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
             CASE WHEN $8 = 'ok' THEN NOW() ELSE NULL END, NOW())
     ON CONFLICT (code) DO UPDATE SET
       title = CASE
         WHEN EXCLUDED.status = 'ok' THEN EXCLUDED.title
         ELSE COALESCE(EXCLUDED.title, av_metadata.title)
       END,
       title_zh = CASE
         WHEN EXCLUDED.status = 'ok' THEN EXCLUDED.title_zh
         ELSE COALESCE(EXCLUDED.title_zh, av_metadata.title_zh)
       END,
       title_ja = CASE
         WHEN EXCLUDED.status = 'ok' THEN EXCLUDED.title_ja
         ELSE COALESCE(EXCLUDED.title_ja, av_metadata.title_ja)
       END,
       actresses = CASE
         WHEN EXCLUDED.status = 'ok' THEN COALESCE(EXCLUDED.actresses, '{}')
         WHEN EXCLUDED.actresses IS NOT NULL AND cardinality(EXCLUDED.actresses) > 0
           THEN EXCLUDED.actresses
         ELSE av_metadata.actresses
       END,
       cover_path = COALESCE(EXCLUDED.cover_path, av_metadata.cover_path),
       cover_source = COALESCE(EXCLUDED.cover_source, av_metadata.cover_source),
       status = EXCLUDED.status,
       error = EXCLUDED.error,
       scraped_at = CASE
         WHEN EXCLUDED.status = 'ok' THEN NOW()
         ELSE av_metadata.scraped_at
       END,
       updated_at = NOW()`,
    [
      row.code,
      row.title ?? null,
      row.title_zh ?? null,
      row.title_ja ?? null,
      row.actresses ?? null,
      row.cover_path ?? null,
      row.cover_source ?? null,
      row.status,
      row.error ?? null,
    ],
  );
}

export async function enqueueCodes(
  codes: string[],
  priority = 0,
  opts?: { overwrite?: boolean; scrapeMode?: string | null },
): Promise<{ enqueued: number; skipped: number }> {
  const overwrite = Boolean(opts?.overwrite);
  const allowed = new Set([
    "av",
    "uncensored",
    "mgstage",
    "fc2",
    "chinese",
    "western",
  ]);
  const scrapeMode =
    opts?.scrapeMode && allowed.has(String(opts.scrapeMode))
      ? String(opts.scrapeMode)
      : null;

  // 规范化 + 去重
  const unique: string[] = [];
  const seen = new Set<string>();
  let skipped = 0;
  for (const raw of codes) {
    const code = normalizeCode(raw);
    if (!code) {
      skipped += 1;
      continue;
    }
    if (seen.has(code)) continue;
    seen.add(code);
    unique.push(code);
  }
  if (!unique.length) return { enqueued: 0, skipped };

  // 一次查出已有 meta，决定跳过 / 入队
  const { rows: metaRows } = await pool.query<{
    code: string;
    status: string;
    cover_path: string | null;
  }>(
    `SELECT code, status, cover_path
     FROM av_metadata
     WHERE code = ANY($1)`,
    [unique],
  );
  const metaMap = new Map(metaRows.map((r) => [r.code, r]));

  // 库里 ok 且有 cover_path 的，再确认磁盘正式文件存在；仅有 .part / 文件缺失则仍入队重下
  const maybeSkip: string[] = [];
  const toEnqueue: string[] = [];
  for (const code of unique) {
    const existing = metaMap.get(code);
    if (!overwrite && existing?.status === "ok" && existing.cover_path) {
      maybeSkip.push(code);
      continue;
    }
    toEnqueue.push(code);
  }
  if (maybeSkip.length) {
    const flags = await Promise.all(maybeSkip.map((c) => hasLocalCover(c)));
    for (let i = 0; i < maybeSkip.length; i++) {
      if (flags[i]) skipped += 1;
      else toEnqueue.push(maybeSkip[i]);
    }
  }
  if (!toEnqueue.length) return { enqueued: 0, skipped };

  // 批量入队；overwrite 入队时 force_overwrite，worker 按任务覆盖
  await pool.query(
    `INSERT INTO av_scrape_queue (code, priority, status, scrape_mode, force_overwrite, updated_at)
     SELECT c, $2, 'pending', $3, $4, NOW()
     FROM unnest($1::text[]) AS c
     ON CONFLICT (code) WHERE status = 'pending' DO UPDATE SET
       priority = GREATEST(av_scrape_queue.priority, EXCLUDED.priority),
       scrape_mode = COALESCE(EXCLUDED.scrape_mode, av_scrape_queue.scrape_mode),
       force_overwrite = av_scrape_queue.force_overwrite OR EXCLUDED.force_overwrite,
       updated_at = NOW()`,
    [toEnqueue, priority, scrapeMode, overwrite],
  );

  // 入队即标 pending（含：库里 ok 但本地封面缺失 / 仅有 .part）
  await pool.query(
    `INSERT INTO av_metadata (code, status, error, updated_at)
     SELECT c, 'pending', NULL, NOW()
     FROM unnest($1::text[]) AS c
     ON CONFLICT (code) DO UPDATE SET
       status = 'pending',
       error = NULL,
       updated_at = NOW()`,
    [toEnqueue],
  );

  return { enqueued: toEnqueue.length, skipped };
}

export async function claimNextJobs(
  limit: number,
): Promise<
  Array<{
    id: number;
    code: string;
    attempts: number;
    scrape_mode: string | null;
    force_overwrite: boolean;
  }>
> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const { rows } = await client.query<{
      id: number;
      code: string;
      attempts: number;
      scrape_mode: string | null;
      force_overwrite: boolean;
    }>(
      `WITH picked AS (
         SELECT id
         FROM av_scrape_queue
         WHERE status = 'pending'
         ORDER BY priority DESC, id ASC
         LIMIT $1
         FOR UPDATE SKIP LOCKED
       )
       UPDATE av_scrape_queue q
       SET status = 'running',
           attempts = q.attempts + 1,
           updated_at = NOW()
       FROM picked
       WHERE q.id = picked.id
       RETURNING q.id, q.code, q.attempts, q.scrape_mode, q.force_overwrite`,
      [limit],
    );
    await client.query("COMMIT");
    return rows;
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

export async function finishJob(
  id: number,
  ok: boolean,
  error?: string | null,
): Promise<void> {
  await pool.query(
    `UPDATE av_scrape_queue
     SET status = $2,
         last_error = $3,
         updated_at = NOW()
     WHERE id = $1`,
    [id, ok ? "done" : "error", error ?? null],
  );
}

export type QueueStats = {
  pending: number;
  running: number;
  done: number;
  error: number;
};

export async function getQueueStats(): Promise<QueueStats> {
  const { rows } = await pool.query<{ status: string; n: string }>(
    `SELECT status, COUNT(*)::text AS n
     FROM av_scrape_queue
     GROUP BY status`,
  );
  const out: QueueStats = { pending: 0, running: 0, done: 0, error: 0 };
  for (const r of rows) {
    const n = Number(r.n) || 0;
    if (r.status === "pending") out.pending = n;
    else if (r.status === "running") out.running = n;
    else if (r.status === "done") out.done = n;
    else if (r.status === "error") out.error = n;
  }
  return out;
}

/** 把卡住的 running 收回 pending（worker 重启/崩溃后遗留） */
export async function reclaimRunningJobs(opts?: {
  /** 仅回收超过该秒数未更新的；不传则回收全部 running */
  olderThanSec?: number;
  /** 仍在本进程处理中的 job id，跳过 */
  excludeIds?: number[];
}): Promise<number> {
  const older = opts?.olderThanSec;
  const exclude = (opts?.excludeIds || []).filter((n) => Number.isFinite(n));
  if (older != null && older > 0) {
    const { rowCount } = await pool.query(
      `UPDATE av_scrape_queue
       SET status = 'pending', updated_at = NOW()
       WHERE status = 'running'
         AND updated_at < NOW() - make_interval(secs => $1)
         AND NOT (id = ANY($2::bigint[]))`,
      [older, exclude],
    );
    return rowCount ?? 0;
  }
  const { rowCount } = await pool.query(
    `UPDATE av_scrape_queue
     SET status = 'pending', updated_at = NOW()
     WHERE status = 'running'
       AND NOT (id = ANY($1::bigint[]))`,
    [exclude],
  );
  return rowCount ?? 0;
}

/** 清空等待中 + 进行中；可选一并清完成/失败记录 */
export async function clearQueue(opts?: {
  includeHistory?: boolean;
}): Promise<{ deleted: number }> {
  const includeHistory = Boolean(opts?.includeHistory);
  const { rowCount } = await pool.query(
    includeHistory
      ? `DELETE FROM av_scrape_queue`
      : `DELETE FROM av_scrape_queue WHERE status IN ('pending', 'running')`,
  );
  return { deleted: rowCount ?? 0 };
}

/** 失败任务重新入队为 pending，并强制覆盖原有数据 */
export async function retryFailedJobs(): Promise<{ retried: number }> {
  const { rowCount } = await pool.query(
    `WITH picked AS (
       SELECT DISTINCT ON (q.code) q.id
       FROM av_scrape_queue q
       WHERE q.status = 'error'
         AND NOT EXISTS (
           SELECT 1
           FROM av_scrape_queue p
           WHERE p.code = q.code
             AND p.status IN ('pending', 'running')
         )
       ORDER BY q.code, q.id DESC
     )
     UPDATE av_scrape_queue q
     SET status = 'pending',
         last_error = NULL,
         force_overwrite = true,
         updated_at = NOW()
     FROM picked
     WHERE q.id = picked.id`,
  );
  return { retried: rowCount ?? 0 };
}

export async function listRecentQueue(limit = 30): Promise<
  Array<{
    id: number;
    code: string;
    status: string;
    attempts: number;
    last_error: string | null;
    updated_at: string;
  }>
> {
  const { rows } = await pool.query<{
    id: number;
    code: string;
    status: string;
    attempts: number;
    last_error: string | null;
    updated_at: Date;
  }>(
    `SELECT id, code, status, attempts, last_error, updated_at
     FROM av_scrape_queue
     ORDER BY updated_at DESC
     LIMIT $1`,
    [Math.max(1, Math.min(100, limit))],
  );
  return rows.map((r) => ({
    id: r.id,
    code: r.code,
    status: r.status,
    attempts: r.attempts,
    last_error: r.last_error,
    updated_at:
      r.updated_at instanceof Date
        ? r.updated_at.toISOString()
        : String(r.updated_at),
  }));
}

/** SSIS-001 / FC2-PPV-1234567 → 规范化大写 */
export function normalizeCode(raw: string): string {
  const text = String(raw || "")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "");
  if (!text) return "";
  const fc2 = text.match(/^FC2(?:-?PPV)?-?(\d{5,10})$/i);
  if (fc2) {
    return text.includes("PPV") || /^FC2PPV/i.test(text)
      ? `FC2-PPV-${fc2[1]}`
      : `FC2-${fc2[1]}`;
  }
  const m = text.match(/^([A-Z]{2,10})[-_]?(\d{2,6})$/);
  if (m) return `${m[1]}-${m[2]}`;
  return text;
}
