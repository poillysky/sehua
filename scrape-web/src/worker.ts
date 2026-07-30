import {
  claimNextJobs,
  finishJob,
  getMeta,
  upsertMeta,
  reclaimRunningJobs,
} from "./db.js";
import { scrapeCode } from "./scrape.js";
import { writeLocalMeta } from "./localMeta.js";
import { hasLocalCover } from "./covers.js";
import { readConfig } from "./config.js";

const POLL_MS = Number(process.env.SCRAPE_POLL_MS || 2000);
const DELAY_MS = Number(process.env.SCRAPE_DELAY_MS || 800);
const ENV_CONCURRENCY = Number(process.env.SCRAPE_CONCURRENCY || 3);
const STALE_RUNNING_SEC = Number(process.env.SCRAPE_STALE_RUNNING_SEC || 600);

let timer: ReturnType<typeof setInterval> | null = null;
let running = false;
/** 本进程正在处理的队列 id，回收僵尸时跳过 */
const activeJobIds = new Set<number>();

function clampConcurrency(n: number): number {
  if (!Number.isFinite(n)) return 3;
  return Math.min(8, Math.max(1, Math.floor(n)));
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function processOne(
  job: {
    id: number;
    code: string;
    attempts: number;
    scrape_mode?: string | null;
    force_overwrite?: boolean;
  },
  opts: { overwrite: boolean },
) {
  activeJobIds.add(job.id);
  try {
    const overwrite = Boolean(job.force_overwrite) || opts.overwrite;
    if (!overwrite) {
      const existing = await getMeta(job.code);
      // 必须正式封面文件存在才跳过；仅有 .part / 文件丢了会重下
      if (
        existing?.status === "ok" &&
        existing.cover_path &&
        (await hasLocalCover(job.code))
      ) {
        await finishJob(job.id, true, null);
        console.log(`[scrape] ${job.code} -> skipped (already ok)`);
        return;
      }
    }
    const kind =
      job.scrape_mode &&
      ["av", "uncensored", "mgstage", "fc2", "chinese", "western"].includes(
        job.scrape_mode,
      )
        ? (job.scrape_mode as
            | "av"
            | "uncensored"
            | "mgstage"
            | "fc2"
            | "chinese"
            | "western")
        : undefined;
    const result = await scrapeCode(job.code, { overwrite, kind });
    const status =
      result.status === "skipped" ? "missing" : result.status;
    await upsertMeta(
      {
        code: result.code,
        title: result.title,
        title_zh: result.title_zh,
        title_ja: result.title_ja,
        actresses: result.actresses,
        cover_path: result.cover_path,
        cover_source: result.cover_source,
        status,
        error: result.error ?? null,
      },
      { overwrite },
    );
    if (status === "ok") {
      try {
        const local = await writeLocalMeta(result);
        console.log(
          `[scrape] ${result.code} local meta=${local.metaPath}` +
            (local.coverAbs ? ` cover=${local.coverAbs}` : ""),
        );
      } catch (err) {
        console.warn(
          `[scrape] ${result.code} local meta write failed:`,
          err instanceof Error ? err.message : err,
        );
      }
    }
    // 仅 ok 算队列完成；missing/error 进「失败」，便于重试
    await finishJob(job.id, status === "ok", result.error ?? null);
    console.log(
      `[scrape] ${result.code} -> ${status}${result.error ? ` (${result.error})` : ""}`,
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    await upsertMeta({
      code: job.code,
      status: "error",
      error: msg,
    });
    await finishJob(job.id, false, msg);
    console.error(`[scrape] ${job.code} failed:`, msg);
  } finally {
    activeJobIds.delete(job.id);
  }
}

async function tick() {
  if (running) return;
  running = true;
  try {
    const n = await reclaimRunningJobs({
      olderThanSec: STALE_RUNNING_SEC,
      excludeIds: [...activeJobIds],
    });
    if (n > 0) {
      console.log(`[scrape] reclaimed ${n} stale running job(s)`);
    }
    const cfg = await readConfig();
    const concurrency = clampConcurrency(
      Number(cfg.scrapeConcurrency ?? ENV_CONCURRENCY),
    );
    const jobs = await claimNextJobs(concurrency);
    if (!jobs.length) return;
    const overwriteDefault = Boolean(cfg.overwriteDefault);
    await Promise.all(
      jobs.map(async (job, i) => {
        if (DELAY_MS > 0 && i > 0) await sleep(DELAY_MS * i);
        await processOne(job, { overwrite: overwriteDefault });
      }),
    );
  } catch (err) {
    console.error("[scrape] worker tick error:", err);
  } finally {
    running = false;
  }
}

export function startWorker(): void {
  if (timer) return;
  console.log(
    `[scrape] worker started poll=${POLL_MS}ms stagger=${DELAY_MS}ms (concurrency from config)`,
  );
  void (async () => {
    const n = await reclaimRunningJobs({ excludeIds: [...activeJobIds] });
    if (n > 0) {
      console.log(`[scrape] startup reclaimed ${n} running job(s)`);
    }
    await tick();
  })();
  timer = setInterval(() => {
    void tick();
  }, POLL_MS);
}

export function stopWorker(): void {
  if (timer) clearInterval(timer);
  timer = null;
  console.log("[scrape] worker stopped");
}

export function isWorkerRunning(): boolean {
  return Boolean(timer);
}

/** 本进程当前实际并行数（≤ 配置并发） */
export function getActiveJobCount(): number {
  return activeJobIds.size;
}
