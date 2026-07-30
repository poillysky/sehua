import express from "express";
import fs from "node:fs/promises";
import path from "node:path";
import { applyProxy, getActiveProxy } from "./proxy.js";
import { applyFlareSolverr, getFlareSolverrUrl } from "./flaresolverr.js";
import { proxyFromEnv, readConfig, writeConfig, configExists } from "./config.js";
import {
  ensureSchema,
  enqueueCodes,
  getMeta,
  getQueueStats,
  listRecentQueue,
  normalizeCode,
  pool,
  upsertMeta,
  clearQueue,
  retryFailedJobs,
  reclaimRunningJobs,
} from "./db.js";
import {
  cleanupCoverPartFiles,
  ensureCoversDir,
  resolveCoverPublicRel,
} from "./covers.js";
import { ensureMetaDir, writeLocalMeta } from "./localMeta.js";
import { scrapeCode } from "./scrape.js";
import { startWorker, stopWorker, isWorkerRunning, getActiveJobCount } from "./worker.js";
import {
  applyMonitorFromConfig,
  getMonitorStatus,
  isMonitorRunning,
} from "./monitor.js";
import {
  normalizeCodeKind,
  probeSource,
  SOURCE_DEFS,
  toSourceCards,
  type SourceId,
} from "./sources/registry.js";
import { getLogs, installScrapeLogCapture } from "./logBuffer.js";
import {
  applyDataDirsFromConfig,
  getCoversDir,
  getCoversDirConfigured,
  getMetaDirConfigured,
  setDataDirs,
} from "./paths.js";

installScrapeLogCapture();

const PORT = Number(process.env.PORT || 9209);
const API_TOKEN = (process.env.SCRAPE_API_TOKEN || "").trim();

function auth(
  req: express.Request,
  res: express.Response,
  next: express.NextFunction,
) {
  if (!API_TOKEN) return next();
  const header = req.header("authorization") || "";
  const token = header.startsWith("Bearer ")
    ? header.slice(7).trim()
    : (req.header("x-api-token") || "").trim();
  if (token !== API_TOKEN) {
    res.status(401).json({ error: "unauthorized" });
    return;
  }
  next();
}

async function initProxy(): Promise<void> {
  if (await configExists()) {
    const cfg = await readConfig();
    applyProxy(cfg.proxyUrl);
    applyFlareSolverr(cfg.flareSolverrUrl);
    return;
  }
  applyProxy(proxyFromEnv());
  applyFlareSolverr(process.env.FLARESOLVERR_URL || "");
}

function isSourceId(id: string): id is SourceId {
  return SOURCE_DEFS.some((d) => d.id === id);
}

async function main() {
  const cfgBoot = await readConfig();
  applyDataDirsFromConfig(cfgBoot);
  await ensureSchema();
  await ensureCoversDir();
  const cleanedParts = await cleanupCoverPartFiles();
  if (cleanedParts > 0) {
    console.log(`[scrape-web] cleaned ${cleanedParts} leftover *.part cover files`);
  }
  await ensureMetaDir();
  await initProxy();

  const app = express();
  app.use(express.json({ limit: "1mb" }));

  app.get("/health", async (_req, res) => {
    try {
      await pool.query("SELECT 1");
      const proxy = getActiveProxy();
      res.json({
        ok: true,
        service: "scrape-web",
        proxy: proxy || null,
        proxyEnabled: Boolean(proxy),
      });
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  });

  app.get("/api/config", auth, async (_req, res) => {
    const cfg = await readConfig();
    applyDataDirsFromConfig(cfg);
    const active = getActiveProxy();
    res.json({
      proxyUrl: cfg.proxyUrl || active || "",
      activeProxy: active || null,
      proxyEnabled: Boolean(active),
      flareSolverrUrl: cfg.flareSolverrUrl || getFlareSolverrUrl() || "",
      flareSolverrEnabled: Boolean(getFlareSolverrUrl()),
      overwriteDefault: cfg.overwriteDefault,
      autoWorker: cfg.autoWorker,
      autoScope: cfg.autoScope,
      monitorEnabled: cfg.monitorEnabled,
      monitorIntervalMin: cfg.monitorIntervalMin,
      scrapeConcurrency: cfg.scrapeConcurrency,
      monitorPrefixes: cfg.monitorPrefixes,
      monitorTargets: cfg.monitorTargets,
      monitorRunning: isMonitorRunning(),
      monitor: getMonitorStatus(),
      priorityByKind: cfg.priorityByKind,
      coversDir: getCoversDirConfigured(),
      metaDir: getMetaDirConfigured(),
      updatedAt: cfg.updatedAt || null,
      envFallback: proxyFromEnv() || null,
      sources: toSourceCards(cfg.sources),
    });
  });

  app.put("/api/config", auth, async (req, res) => {
    const proxyUrl =
      req.body?.proxyUrl !== undefined
        ? String(req.body.proxyUrl)
        : undefined;
    if (proxyUrl !== undefined && proxyUrl.trim()) {
      try {
        // eslint-disable-next-line no-new
        new URL(proxyUrl.trim());
      } catch {
        res.status(400).json({
          error: "代理地址无效，示例：http://127.0.0.1:7890",
        });
        return;
      }
    }
    const flareSolverrUrl =
      req.body?.flareSolverrUrl !== undefined
        ? String(req.body.flareSolverrUrl)
        : undefined;
    if (flareSolverrUrl !== undefined && flareSolverrUrl.trim()) {
      try {
        // eslint-disable-next-line no-new
        new URL(flareSolverrUrl.trim());
      } catch {
        res.status(400).json({
          error: "FlareSolverr 地址无效，示例：http://127.0.0.1:8191/v1",
        });
        return;
      }
    }
    let coversDir: string | undefined;
    let metaDir: string | undefined;
    try {
      if (req.body?.coversDir !== undefined) {
        coversDir = String(req.body.coversDir);
      }
      if (req.body?.metaDir !== undefined) {
        metaDir = String(req.body.metaDir);
      }
    } catch (err) {
      res.status(400).json({
        error: err instanceof Error ? err.message : "目录无效",
      });
      return;
    }
    try {
      const saved = await writeConfig({
        proxyUrl: proxyUrl !== undefined ? proxyUrl.trim() : undefined,
        flareSolverrUrl:
          flareSolverrUrl !== undefined ? flareSolverrUrl.trim() : undefined,
        overwriteDefault:
          req.body?.overwriteDefault !== undefined
            ? Boolean(req.body.overwriteDefault)
            : undefined,
        autoWorker:
          req.body?.autoWorker !== undefined
            ? Boolean(req.body.autoWorker)
            : undefined,
        autoScope:
          req.body?.autoScope !== undefined ? req.body.autoScope : undefined,
        monitorEnabled:
          req.body?.monitorEnabled !== undefined
            ? Boolean(req.body.monitorEnabled)
            : undefined,
        monitorIntervalMin:
          req.body?.monitorIntervalMin !== undefined
            ? Number(req.body.monitorIntervalMin)
            : undefined,
        scrapeConcurrency:
          req.body?.scrapeConcurrency !== undefined
            ? Number(req.body.scrapeConcurrency)
            : undefined,
        monitorPrefixes:
          req.body?.monitorPrefixes !== undefined
            ? req.body.monitorPrefixes
            : undefined,
        monitorTargets:
          req.body?.monitorTargets !== undefined
            ? req.body.monitorTargets
            : undefined,
        priorityByKind:
          req.body?.priorityByKind !== undefined
            ? req.body.priorityByKind
            : undefined,
        coversDir,
        metaDir,
        sources: req.body?.sources,
      });
      applyDataDirsFromConfig(saved);
      setDataDirs({
        coversDir: saved.coversDir,
        metaDir: saved.metaDir,
      });
      await ensureCoversDir();
      await ensureMetaDir();
      if (proxyUrl !== undefined) applyProxy(saved.proxyUrl);
      if (flareSolverrUrl !== undefined) {
        applyFlareSolverr(saved.flareSolverrUrl);
      }
      if (saved.autoWorker) startWorker();
      else stopWorker();
      await applyMonitorFromConfig();
      res.json({
        ok: true,
        proxyUrl: saved.proxyUrl,
        activeProxy: getActiveProxy() || null,
        proxyEnabled: Boolean(getActiveProxy()),
        flareSolverrUrl: saved.flareSolverrUrl || "",
        flareSolverrEnabled: Boolean(getFlareSolverrUrl()),
        overwriteDefault: saved.overwriteDefault,
        autoWorker: saved.autoWorker,
        autoScope: saved.autoScope,
        monitorEnabled: saved.monitorEnabled,
        monitorIntervalMin: saved.monitorIntervalMin,
        scrapeConcurrency: saved.scrapeConcurrency,
        monitorPrefixes: saved.monitorPrefixes,
        monitorTargets: saved.monitorTargets,
        monitorRunning: isMonitorRunning(),
        monitor: getMonitorStatus(),
        workerRunning: isWorkerRunning(),
        priorityByKind: saved.priorityByKind,
        coversDir: getCoversDirConfigured(),
        metaDir: getMetaDirConfigured(),
        updatedAt: saved.updatedAt,
        sources: toSourceCards(saved.sources),
        message: "已保存",
      });
    } catch (err) {
      res.status(400).json({
        error: err instanceof Error ? err.message : String(err),
      });
    }
  });

  app.get("/api/status", auth, async (_req, res) => {
    const cfg = await readConfig();
    const [queue, recent] = await Promise.all([
      getQueueStats(),
      listRecentQueue(40),
    ]);
    res.json({
      ok: true,
      autoWorker: cfg.autoWorker,
      workerRunning: isWorkerRunning(),
      overwriteDefault: cfg.overwriteDefault,
      scrapeConcurrency: cfg.scrapeConcurrency,
      activeJobs: getActiveJobCount(),
      autoScope: cfg.autoScope,
      monitorEnabled: cfg.monitorEnabled,
      monitorIntervalMin: cfg.monitorIntervalMin,
      monitorRunning: isMonitorRunning(),
      monitor: getMonitorStatus(),
      coversDir: getCoversDirConfigured(),
      metaDir: getMetaDirConfigured(),
      proxy: getActiveProxy() || null,
      queue,
      recent,
      logs: getLogs(100),
    });
  });

  /** 停止爬虫：停 worker，并关掉自动消费（避免被配置再次拉起） */
  app.post("/api/worker/stop", auth, async (_req, res) => {
    stopWorker();
    const saved = await writeConfig({ autoWorker: false });
    res.json({
      ok: true,
      autoWorker: saved.autoWorker,
      workerRunning: isWorkerRunning(),
      message: "已停止爬虫",
    });
  });

  /** 启动爬虫：开自动消费并启动 worker */
  app.post("/api/worker/start", auth, async (_req, res) => {
    const saved = await writeConfig({ autoWorker: true });
    startWorker();
    res.json({
      ok: true,
      autoWorker: saved.autoWorker,
      workerRunning: isWorkerRunning(),
      message: "已启动爬虫",
    });
  });

  /** 清空队列：默认清等待+进行中；history=1 时含完成/失败 */
  app.post("/api/queue/clear", auth, async (req, res) => {
    const includeHistory =
      String(req.query.history || "") === "1" ||
      req.body?.history === true ||
      req.body?.history === 1 ||
      req.body?.history === "1";
    const result = await clearQueue({ includeHistory });
    const queue = await getQueueStats();
    res.json({
      ok: true,
      ...result,
      includeHistory,
      queue,
      message: includeHistory
        ? `已清空全部队列记录（${result.deleted}）`
        : `已清空等待/进行中（${result.deleted}）`,
    });
  });

  /** 失败重试：error → pending，强制覆盖原有数据 */
  app.post("/api/queue/retry-failed", auth, async (_req, res) => {
    const result = await retryFailedJobs();
    const cfg = await readConfig();
    if (result.retried > 0 && cfg.autoWorker && !isWorkerRunning()) {
      startWorker();
    }
    const queue = await getQueueStats();
    res.json({
      ok: true,
      ...result,
      queue,
      workerRunning: isWorkerRunning(),
      message:
        result.retried > 0
          ? `已重试 ${result.retried} 条（覆盖模式）`
          : "没有可重试的失败任务",
    });
  });

  app.get("/api/sources", auth, async (_req, res) => {
    const cfg = await readConfig();
    res.json({
      updatedAt: cfg.updatedAt || null,
      sources: toSourceCards(cfg.sources),
    });
  });

  app.put("/api/sources/:id", auth, async (req, res) => {
    const id = String(req.params.id || "");
    if (!isSourceId(id)) {
      res.status(404).json({ error: "unknown source" });
      return;
    }
    const body = req.body || {};
    if (body.baseUrl !== undefined && String(body.baseUrl).trim()) {
      try {
        // eslint-disable-next-line no-new
        new URL(String(body.baseUrl).trim());
      } catch {
        res.status(400).json({ error: "无效 URL" });
        return;
      }
    }
    const patch: Record<string, unknown> = {};
    if (body.enabled !== undefined) patch.enabled = Boolean(body.enabled);
    if (body.baseUrl !== undefined) patch.baseUrl = String(body.baseUrl).trim();
    if (body.cookie !== undefined) patch.cookie = String(body.cookie);
    if (body.userAgent !== undefined) patch.userAgent = String(body.userAgent);
    if (body.proxyMode !== undefined) patch.proxyMode = String(body.proxyMode);
    if (body.timeoutMs !== undefined) patch.timeoutMs = Number(body.timeoutMs);
    if (body.retry !== undefined) patch.retry = Number(body.retry);
    if (body.useFlareSolverr !== undefined) {
      patch.useFlareSolverr = Boolean(body.useFlareSolverr);
    }
    if (body.cooldownUntil !== undefined) {
      patch.cooldownUntil = body.cooldownUntil
        ? String(body.cooldownUntil)
        : null;
    }
    const saved = await writeConfig({ sources: { [id]: patch } });
    res.json({
      ok: true,
      source: toSourceCards(saved.sources).find((s) => s.id === id),
      sources: toSourceCards(saved.sources),
      updatedAt: saved.updatedAt,
    });
  });

  app.post("/api/sources/test", auth, async (req, res) => {
    const only = req.body?.id ? String(req.body.id) : "";
    const cfg = await readConfig();
    const ids = only
      ? isSourceId(only)
        ? [only]
        : []
      : (SOURCE_DEFS.map((d) => d.id) as SourceId[]);
    if (only && !ids.length) {
      res.status(404).json({ error: "unknown source" });
      return;
    }

    const patches: Partial<
      Record<SourceId, Partial<(typeof cfg.sources)[SourceId]>>
    > = {};
    for (const id of ids) {
      const result = await probeSource(id, cfg.sources[id]);
      patches[id] = result;
    }
    const saved = await writeConfig({ sources: patches });
    res.json({
      ok: true,
      updatedAt: saved.updatedAt,
      sources: toSourceCards(saved.sources),
    });
  });

  app.get("/covers/:name", async (req, res, next) => {
    // 仅拦截扁平 /covers/CODE.jpg → 定位分级文件；多级路径交给 static
    const name = String(req.params.name || "");
    if (!name || name.includes("/") || !/\.jpe?g$/i.test(name)) {
      next();
      return;
    }
    try {
      const code = normalizeCode(name.replace(/\.jpe?g$/i, ""));
      if (!code) {
        next();
        return;
      }
      const rel = await resolveCoverPublicRel(code);
      const abs = path.join(getCoversDir(), ...rel.split("/"));
      await fs.access(abs);
      res.setHeader("Cache-Control", "public, max-age=604800");
      res.sendFile(abs);
    } catch {
      next();
    }
  });

  app.use("/covers", (req, res, next) => {
    express.static(getCoversDir(), {
      fallthrough: false,
      maxAge: "7d",
      etag: true,
    })(req, res, next);
  });

  app.get("/api/meta/:code", auth, async (req, res) => {
    const code = normalizeCode(req.params.code || "");
    if (!code) {
      res.status(400).json({ error: "invalid code" });
      return;
    }
    const row = await getMeta(code);
    if (!row) {
      res.status(404).json({ error: "not found", code });
      return;
    }
    res.json(row);
  });

  // 必须在 /api/scrape/:code 之前，否则 batch 会被当成番号
  app.post("/api/scrape/batch", auth, async (req, res) => {
    const codes = Array.isArray(req.body?.codes) ? req.body.codes : [];
    const priority = Number(req.body?.priority || 0) || 0;
    const overwrite =
      req.body?.overwrite === true ||
      req.body?.overwrite === 1 ||
      req.body?.overwrite === "1";
    if (!codes.length) {
      res.status(400).json({ error: "codes required" });
      return;
    }
    const clipped = codes.map(String).slice(0, 500);
    const scrapeMode =
      typeof req.body?.kind === "string" ? String(req.body.kind) : null;
    const result = await enqueueCodes(clipped, priority, {
      overwrite,
      scrapeMode,
    });
    res.json({ ...result, received: clipped.length, overwrite });
  });

  app.post("/api/scrape/:code", auth, async (req, res) => {
    const rawParam = String(req.params.code || "").trim();
    if (/^(batch|health|status|config|sources)$/i.test(rawParam)) {
      res.status(404).json({ error: "not found" });
      return;
    }
    const code = normalizeCode(rawParam);
    if (!code) {
      res.status(400).json({ error: "invalid code" });
      return;
    }
    const sync = String(req.query.sync || "") === "1";
    const overwrite =
      String(req.query.overwrite || "") === "1" ||
      req.body?.overwrite === true ||
      req.body?.overwrite === 1 ||
      req.body?.overwrite === "1";
    if (!sync) {
      const scrapeMode =
        typeof req.body?.kind === "string" ? String(req.body.kind) : null;
      const result = await enqueueCodes([code], 10, {
        overwrite,
        scrapeMode,
      });
      res.json({ queued: true, code, overwrite, ...result });
      return;
    }
    // 同步刮削一律覆盖：重下封面、覆盖库字段、写本地 meta
    const kindRaw = req.body?.kind ?? req.query.kind;
    const scraped = await scrapeCode(code, {
      overwrite: true,
      kind:
        kindRaw !== undefined && kindRaw !== null && String(kindRaw).trim()
          ? normalizeCodeKind(kindRaw)
          : undefined,
    });
    const status =
      scraped.status === "skipped" ? "missing" : scraped.status;
    await upsertMeta(
      {
        code: scraped.code,
        title: scraped.title,
        title_zh: scraped.title_zh,
        title_ja: scraped.title_ja,
        actresses: scraped.actresses,
        cover_path: scraped.cover_path,
        cover_source: scraped.cover_source,
        status,
        error: scraped.error ?? null,
      },
      { overwrite: true },
    );
    let local: { metaPath?: string; coverAbs?: string | null } = {};
    if (status === "ok") {
      try {
        local = await writeLocalMeta(scraped);
      } catch (err) {
        console.warn(
          `[scrape] local meta write failed:`,
          err instanceof Error ? err.message : err,
        );
      }
    }
    res.json({
      ...scraped,
      overwrite: true,
      local_meta: local.metaPath || null,
      local_cover: local.coverAbs || null,
    });
  });

  const cfg0 = await readConfig();
  // 启动时清掉上次进程遗留的 running，避免「进行中」虚高
  {
    const n = await reclaimRunningJobs();
    if (n > 0) {
      console.log(`[scrape-web] boot reclaimed ${n} stale running job(s)`);
    }
  }
  if (cfg0.autoWorker) startWorker();
  else console.log("[scrape] autoWorker=off, queue worker not started");
  await applyMonitorFromConfig();

  const server = app.listen(PORT, () => {
    console.log(
      `[scrape-web] listening :${PORT} covers=${getCoversDirConfigured()} meta=${getMetaDirConfigured()}`,
    );
  });

  const shutdown = () => {
    stopWorker();
    server.close(() => {
      void pool.end().finally(() => process.exit(0));
    });
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  console.error("[scrape-web] fatal:", err);
  process.exit(1);
});
