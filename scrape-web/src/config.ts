import fs from "node:fs/promises";
import path from "node:path";

import {
  defaultSourceConfig,
  mergePriorityByKind,
  mergeSourcesConfig,
  normalizeCodeKind,
  applySourcePatch,
  SOURCE_DEFS,
  type CodeKind,
  type PriorityByKind,
  type SourceConfig,
  type SourceId,
} from "./sources/registry.js";
import {
  DEFAULT_COVERS_DIR,
  DEFAULT_META_DIR,
  normalizeDataPath,
} from "./paths.js";

export type AutoScope = {
  /** 一级：日本 / 国产 / 欧美 */
  region: string;
  /** 二级：有码 / 无码 等；空=该分区全部 */
  board: string;
  /** 厂牌前缀；空=该板块全部厂牌 */
  prefix: string;
  /** 具体番号；空=该厂牌全部 */
  code: string;
};

export type MonitorTarget = AutoScope & {
  id: string;
  /** 解析后的厂牌前缀列表（供 scrape-web 扫描） */
  prefixes: string[];
  /**
   * 刮削类型模式：有码/无码/素人/FC2/国产/欧美
   * 缺省按番号自动识别
   */
  mode?: CodeKind;
};

export type ScrapeConfig = {
  proxyUrl: string;
  /** FlareSolverr 地址，如 http://127.0.0.1:8191/v1（对齐 mdc-ng） */
  flareSolverrUrl: string;
  /** 入队/表单默认是否覆盖已有结果 */
  overwriteDefault: boolean;
  /** 队列自动消费（worker） */
  autoWorker: boolean;
  /** 手动入队作用域（多级板块） */
  autoScope: AutoScope;
  /** 监控模式总开关 */
  monitorEnabled: boolean;
  /** 监控间隔（分钟） */
  monitorIntervalMin: number;
  /** worker 并发数（1–8） */
  scrapeConcurrency: number;
  /** 监控板块列表（多条目） */
  monitorTargets: MonitorTarget[];
  /** @deprecated 兼容旧配置，优先用 monitorTargets */
  monitorPrefixes: string[];
  /** 各番号类型的源优先级（可在数据源页配置；默认封面优先） */
  priorityByKind: PriorityByKind;
  /** 容器友好路径，如 /data/covers */
  coversDir: string;
  /** 容器友好路径，如 /data/meta */
  metaDir: string;
  sources: Record<SourceId, SourceConfig>;
  updatedAt?: string;
};

export const DEFAULT_AUTO_SCOPE: AutoScope = {
  region: "日本",
  board: "",
  prefix: "",
  code: "",
};

function normalizeAutoScope(raw: unknown): AutoScope {
  const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    region: String(o.region || DEFAULT_AUTO_SCOPE.region).trim() || "日本",
    board: String(o.board || "").trim(),
    prefix: String(o.prefix || "").trim().toUpperCase(),
    code: String(o.code || "").trim().toUpperCase(),
  };
}

function normalizeMonitorPrefixes(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const x of raw) {
    const p = String(x || "")
      .trim()
      .toUpperCase();
    if (!p || seen.has(p)) continue;
    seen.add(p);
    out.push(p);
  }
  return out;
}

function newMonitorId(): string {
  return `mt_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function normalizeMonitorTargets(
  raw: unknown,
  fallbackScope: AutoScope,
  fallbackPrefixes: string[],
): MonitorTarget[] {
  const list: MonitorTarget[] = [];
  if (Array.isArray(raw)) {
    for (const item of raw) {
      if (!item || typeof item !== "object") continue;
      const o = item as Record<string, unknown>;
      const scope = normalizeAutoScope(o);
      const prefixes = normalizeMonitorPrefixes(o.prefixes);
      list.push({
        id: String(o.id || "").trim() || newMonitorId(),
        ...scope,
        mode: o.mode !== undefined ? normalizeCodeKind(o.mode) : undefined,
        prefixes:
          prefixes.length > 0
            ? prefixes
            : scope.prefix
              ? [scope.prefix]
              : [],
      });
    }
  }
  if (list.length === 0 && fallbackPrefixes.length > 0) {
    list.push({
      id: newMonitorId(),
      ...fallbackScope,
      prefixes: fallbackPrefixes,
    });
  }
  return list;
}

function normalizeIntervalMin(raw: unknown): number {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return 15;
  return Math.min(Math.floor(n), 24 * 60);
}

function normalizeConcurrency(raw: unknown): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 3;
  return Math.min(8, Math.max(1, Math.floor(n)));
}

const CONFIG_DIR =
  process.env.SCRAPE_CONFIG_DIR ||
  path.resolve(process.cwd(), "data");
const CONFIG_PATH = path.join(CONFIG_DIR, "scrape-config.json");

export async function configExists(): Promise<boolean> {
  try {
    await fs.access(CONFIG_PATH);
    return true;
  } catch {
    return false;
  }
}

export async function readConfig(): Promise<ScrapeConfig> {
  try {
    const raw = await fs.readFile(CONFIG_PATH, "utf8");
    const data = JSON.parse(raw) as Partial<ScrapeConfig> & {
      sources?: Partial<Record<string, Partial<SourceConfig>>>;
    };
    const autoScope = normalizeAutoScope(data.autoScope);
    const monitorPrefixes = normalizeMonitorPrefixes(data.monitorPrefixes);
    const monitorTargets = normalizeMonitorTargets(
      data.monitorTargets,
      autoScope,
      monitorPrefixes,
    );
    return {
      proxyUrl: String(data.proxyUrl || "").trim(),
      flareSolverrUrl: String(
        data.flareSolverrUrl || process.env.FLARESOLVERR_URL || "",
      ).trim(),
      overwriteDefault:
        data.overwriteDefault === undefined
          ? false
          : Boolean(data.overwriteDefault),
      autoWorker:
        data.autoWorker === undefined ? true : Boolean(data.autoWorker),
      autoScope,
      monitorEnabled: Boolean(data.monitorEnabled),
      monitorIntervalMin: normalizeIntervalMin(data.monitorIntervalMin),
      scrapeConcurrency: normalizeConcurrency(
        data.scrapeConcurrency ?? process.env.SCRAPE_CONCURRENCY ?? 3,
      ),
      monitorTargets,
      monitorPrefixes:
        monitorPrefixes.length > 0
          ? monitorPrefixes
          : monitorTargets.flatMap((t) => t.prefixes),
      priorityByKind: mergePriorityByKind(data.priorityByKind),
      coversDir: normalizeDataPath(
        String(data.coversDir || process.env.COVERS_DIR || ""),
        DEFAULT_COVERS_DIR,
      ),
      metaDir: normalizeDataPath(
        String(data.metaDir || process.env.META_DIR || ""),
        DEFAULT_META_DIR,
      ),
      sources: mergeSourcesConfig(data.sources),
      updatedAt: data.updatedAt,
    };
  } catch {
    return {
      proxyUrl: "",
      flareSolverrUrl: String(process.env.FLARESOLVERR_URL || "").trim(),
      overwriteDefault: false,
      autoWorker: true,
      autoScope: { ...DEFAULT_AUTO_SCOPE },
      monitorEnabled: false,
      monitorIntervalMin: 15,
      scrapeConcurrency: normalizeConcurrency(
        process.env.SCRAPE_CONCURRENCY ?? 3,
      ),
      monitorTargets: [],
      monitorPrefixes: [],
      priorityByKind: mergePriorityByKind(undefined),
      coversDir: normalizeDataPath(
        process.env.COVERS_DIR || "",
        DEFAULT_COVERS_DIR,
      ),
      metaDir: normalizeDataPath(process.env.META_DIR || "", DEFAULT_META_DIR),
      sources: mergeSourcesConfig(undefined),
    };
  }
}

function patchSources(
  prev: Record<SourceId, SourceConfig>,
  patches: Partial<Record<string, Partial<SourceConfig>>>,
): Record<SourceId, SourceConfig> {
  const next = { ...prev };
  for (const def of SOURCE_DEFS) {
    const patch = patches[def.id];
    if (!patch) continue;
    const cur = next[def.id] || defaultSourceConfig(def.id);
    next[def.id] = applySourcePatch(cur, patch as Partial<SourceConfig>);
  }
  return next;
}

export async function writeConfig(
  input: Partial<{
    proxyUrl: string;
    flareSolverrUrl: string;
    overwriteDefault: boolean;
    autoWorker: boolean;
    autoScope: Partial<AutoScope> | AutoScope;
    monitorEnabled: boolean;
    monitorIntervalMin: number;
    scrapeConcurrency: number;
    monitorPrefixes: string[];
    monitorTargets: MonitorTarget[];
    priorityByKind: PriorityByKind;
    coversDir: string;
    metaDir: string;
    sources: Partial<Record<string, Partial<SourceConfig>>>;
  }>,
): Promise<ScrapeConfig> {
  const prev = await readConfig();
  const monitorTargets =
    input.monitorTargets !== undefined
      ? normalizeMonitorTargets(input.monitorTargets, prev.autoScope, [])
      : prev.monitorTargets;
  const monitorPrefixes =
    input.monitorPrefixes !== undefined
      ? normalizeMonitorPrefixes(input.monitorPrefixes)
      : input.monitorTargets !== undefined
        ? monitorTargets.flatMap((t) => t.prefixes)
        : prev.monitorPrefixes;
  const next: ScrapeConfig = {
    proxyUrl:
      input.proxyUrl !== undefined
        ? String(input.proxyUrl).trim()
        : prev.proxyUrl,
    flareSolverrUrl:
      input.flareSolverrUrl !== undefined
        ? String(input.flareSolverrUrl).trim()
        : prev.flareSolverrUrl,
    overwriteDefault:
      input.overwriteDefault !== undefined
        ? Boolean(input.overwriteDefault)
        : prev.overwriteDefault,
    autoWorker:
      input.autoWorker !== undefined
        ? Boolean(input.autoWorker)
        : prev.autoWorker,
    autoScope:
      input.autoScope !== undefined
        ? normalizeAutoScope({ ...prev.autoScope, ...input.autoScope })
        : prev.autoScope,
    monitorEnabled:
      input.monitorEnabled !== undefined
        ? Boolean(input.monitorEnabled)
        : prev.monitorEnabled,
    monitorIntervalMin:
      input.monitorIntervalMin !== undefined
        ? normalizeIntervalMin(input.monitorIntervalMin)
        : prev.monitorIntervalMin,
    scrapeConcurrency:
      input.scrapeConcurrency !== undefined
        ? normalizeConcurrency(input.scrapeConcurrency)
        : prev.scrapeConcurrency,
    monitorTargets,
    monitorPrefixes,
    priorityByKind:
      input.priorityByKind !== undefined
        ? mergePriorityByKind(input.priorityByKind)
        : prev.priorityByKind,
    coversDir:
      input.coversDir !== undefined
        ? normalizeDataPath(String(input.coversDir), prev.coversDir)
        : prev.coversDir,
    metaDir:
      input.metaDir !== undefined
        ? normalizeDataPath(String(input.metaDir), prev.metaDir)
        : prev.metaDir,
    sources:
      input.sources !== undefined
        ? patchSources(prev.sources, input.sources)
        : prev.sources,
    updatedAt: new Date().toISOString(),
  };
  await fs.mkdir(CONFIG_DIR, { recursive: true });
  await fs.writeFile(CONFIG_PATH, JSON.stringify(next, null, 2), "utf8");
  return next;
}

export function proxyFromEnv(): string {
  return (
    process.env.HTTPS_PROXY ||
    process.env.HTTP_PROXY ||
    process.env.ALL_PROXY ||
    process.env.https_proxy ||
    process.env.http_proxy ||
    ""
  ).trim();
}
