import { enqueueCodes, normalizeCode, pool } from "./db.js";
import { readConfig } from "./config.js";
import { startWorker, isWorkerRunning } from "./worker.js";

/** 从文件名粗提取 PREFIX-123（与 backfill 一致） */
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

async function listCodesForPrefix(prefix: string, limit = 2000): Promise<string[]> {
  const p = String(prefix || "")
    .trim()
    .toUpperCase();
  if (!p) return [];
  const { rows } = await pool.query<{ filename: string }>(
    `SELECT DISTINCT r.filename
     FROM ed2k_resources r
     WHERE COALESCE(r.filename, '') <> ''
       AND (
         r.filename ILIKE $1
         OR r.filename ILIKE $2
       )
     ORDER BY r.filename
     LIMIT $3`,
    [
      `${p}-%`,
      `%${p}-%`,
      Math.min(Math.max(limit, 1), 5000),
    ],
  );
  const codes = new Set<string>();
  const needle = `${p}-`;
  for (const row of rows) {
    for (const c of extractCodes(row.filename)) {
      if (c.startsWith(needle)) codes.add(c);
    }
  }
  return Array.from(codes).sort((a, b) => a.localeCompare(b, "en"));
}

let timer: NodeJS.Timeout | null = null;
let ticking = false;
let lastRunAt: string | null = null;
let lastResult: {
  scanned: number;
  enqueued: number;
  skipped: number;
  at: string;
} | null = null;

export function isMonitorRunning(): boolean {
  return Boolean(timer);
}

export function getMonitorStatus() {
  return {
    running: isMonitorRunning(),
    lastRunAt,
    lastResult,
  };
}

export async function runMonitorOnce(): Promise<{
  scanned: number;
  enqueued: number;
  skipped: number;
}> {
  const cfg = await readConfig();
  if (!cfg.monitorEnabled) {
    return { scanned: 0, enqueued: 0, skipped: 0 };
  }

  // 监控始终只补缺，不覆盖已有成功数据
  const overwrite = false;
  let codes: string[] = [];
  let enqueued = 0;
  let skipped = 0;

  const targets = cfg.monitorTargets || [];
  if (targets.length > 0) {
    for (const t of targets) {
      const mode = t.mode; // CodeKind，缺省则入队后自动识别
      let partCodes: string[] = [];
      if (t.code) {
        partCodes = [t.code];
      } else {
        const prefixes =
          t.prefixes?.length > 0
            ? t.prefixes
            : t.prefix
              ? [t.prefix]
              : [];
        for (const p of prefixes) {
          const part = await listCodesForPrefix(p, 2000);
          partCodes.push(...part);
        }
      }
      const uniquePart = Array.from(new Set(partCodes));
      codes.push(...uniquePart);
      const CHUNK = 200;
      for (let i = 0; i < uniquePart.length; i += CHUNK) {
        const chunk = uniquePart.slice(i, i + CHUNK);
        const r = await enqueueCodes(chunk, 0, {
          overwrite,
          scrapeMode: mode || null,
        });
        enqueued += r.enqueued;
        skipped += r.skipped;
      }
    }
  } else {
    // 兼容旧单作用域配置
    const scope = cfg.autoScope;
    if (scope.code) {
      codes = [scope.code];
    } else {
      const prefixes =
        cfg.monitorPrefixes.length > 0
          ? cfg.monitorPrefixes
          : scope.prefix
            ? [scope.prefix]
            : [];
      for (const p of prefixes) {
        const part = await listCodesForPrefix(p, 2000);
        codes.push(...part);
      }
    }
    const uniqueLegacy = Array.from(new Set(codes));
    const CHUNK = 200;
    for (let i = 0; i < uniqueLegacy.length; i += CHUNK) {
      const chunk = uniqueLegacy.slice(i, i + CHUNK);
      const r = await enqueueCodes(chunk, 0, { overwrite });
      enqueued += r.enqueued;
      skipped += r.skipped;
    }
  }

  const unique = Array.from(new Set(codes));

  if (enqueued > 0 && cfg.autoWorker && !isWorkerRunning()) {
    startWorker();
  }

  lastRunAt = new Date().toISOString();
  lastResult = {
    scanned: unique.length,
    enqueued,
    skipped,
    at: lastRunAt,
  };
  console.log(
    `[monitor] scanned=${unique.length} enqueued=${enqueued} skipped=${skipped}`,
  );
  return { scanned: unique.length, enqueued, skipped };
}

async function tick() {
  if (ticking) return;
  ticking = true;
  try {
    const cfg = await readConfig();
    if (!cfg.monitorEnabled) {
      stopMonitor();
      return;
    }
    await runMonitorOnce();
  } catch (err) {
    console.error(
      "[monitor] tick error:",
      err instanceof Error ? err.message : err,
    );
  } finally {
    ticking = false;
  }
}

export async function startMonitor(): Promise<void> {
  const cfg = await readConfig();
  const mins = Math.max(1, Number(cfg.monitorIntervalMin) || 15);
  const ms = mins * 60 * 1000;
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
  console.log(`[monitor] started interval=${mins}min`);
  void tick();
  timer = setInterval(() => {
    void tick();
  }, ms);
}

export function stopMonitor(): void {
  if (timer) clearInterval(timer);
  timer = null;
  console.log("[monitor] stopped");
}

/** 按配置启停；改间隔时重启 */
export async function applyMonitorFromConfig(): Promise<void> {
  const cfg = await readConfig();
  if (cfg.monitorEnabled) {
    if (cfg.autoWorker) startWorker();
    await startMonitor();
  } else {
    stopMonitor();
  }
}
