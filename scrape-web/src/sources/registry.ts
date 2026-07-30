import { undiciFetch } from "./http.js";
import type { ProxyMode } from "../httpContext.js";

export type { ProxyMode };

export type SourceId =
  | "airav"
  | "airav_io"
  | "avbase"
  | "avmoo"
  | "avsox"
  | "carib"
  | "dmm"
  | "fc2"
  | "fc2_hub"
  | "fd2ppv"
  | "freejavbt"
  | "hbox_jp"
  | "jav321"
  | "javbus"
  | "javdb"
  | "javlibrary"
  | "madou"
  | "madouqu"
  | "mgstage"
  | "miss_av"
  | "sevenmmtv"
  | "theporndb"
  | "xiao_huang_shu";

export type SourceStatus = "ok" | "error" | "unknown";

/** 番号/刮削类型（监控「模式」与优先级行） */
export type CodeKind =
  | "av"
  | "uncensored"
  | "mgstage"
  | "fc2"
  | "chinese"
  | "western";

export const CODE_KIND_LABELS: Record<CodeKind, string> = {
  av: "有码",
  uncensored: "无码",
  mgstage: "素人",
  fc2: "FC2",
  chinese: "国产",
  western: "欧美",
};

export const CODE_KINDS: CodeKind[] = [
  "av",
  "uncensored",
  "mgstage",
  "fc2",
  "chinese",
  "western",
];

/** 监控/入队可选模式（默认有码；刮削始终封面优先） */
export const SCRAPE_KIND_OPTIONS: Array<{ id: CodeKind; label: string }> =
  CODE_KINDS.map((id) => ({ id, label: CODE_KIND_LABELS[id] }));

export type PriorityOrders = { meta: SourceId[]; cover: SourceId[] };
export type PriorityByKind = Record<CodeKind, PriorityOrders>;

export type SourceDef = {
  id: SourceId;
  name: string;
  defaultUrl: string;
  probePath: string;
  /** 默认是否启用 */
  defaultEnabled?: boolean;
  /** UI 分组 */
  group: "av" | "fc2" | "chinese" | "other";
};

/** 相对全局代理：跟随 / 强制走代理 / 强制直连 — 见 ProxyMode */

export type SourceConfig = {
  enabled: boolean;
  baseUrl: string;
  /** Cookie 头（javbus/mgstage 等过年龄墙常用） */
  cookie: string;
  /** 空则用默认 Chrome UA；CF 站点可与 cookie 配套固定 */
  userAgent: string;
  proxyMode: ProxyMode;
  /** 0=用环境 SCRAPE_TIMEOUT_MS */
  timeoutMs: number;
  /** 失败额外重试次数（不含首次） */
  retry: number;
  /** 走 FlareSolverr 过 Cloudflare（对齐 mdc-ng） */
  useFlareSolverr: boolean;
  status: SourceStatus;
  lastCheckedAt: string | null;
  lastError: string | null;
  cooldownUntil: string | null;
};

/** 国产常见前缀 */
const CHINESE_PREFIX =
  /^(MD|MKY|PMX|TMY|TZ|CUS|LY|MSD|MSQ|91CM|JVID|DOM|DSUA|EMX|FSOG|HKG|IDG|JD|KCM|LAA|MAD|MAH|MB|MCY|MDC|MDS|ML|MMZ|MPG|MSG|MTVQ|MXJ|MZQ|NHK|NMH|NMS|OMG|PCA|PM|RAS|SAT|SAO|SEX|SMD|TDMY|TG|TMW|UA|WDM|XKVP|XJX|YM|YOK|ZMX)/i;

/** 无码/厂商站 */
const UNCENSORED =
  /^(CARIB(?:BEAN(?:COM)?)?|CARIBPR|1PON(?:DO)?|PACO(?:PACOMAMA)?|HEYZO|TOKYO[-_]?HOT|MURMUR|KIN8|GACHI(?:NCO)?|H0930|C0930|H4610|10MU(?:SUME)?|XXX[-_]?AV|COSPURI)/i;

/**
 * 番号分流：AV / FC2 / 国产 / 无码 / MGStage
 */
export function detectCodeKind(code: string): CodeKind {
  const c = code.trim().toUpperCase();
  if (/^FC2/.test(c)) return "fc2";
  if (UNCENSORED.test(c) || /^\d{6}[-_]\d{2,3}$/.test(c)) return "uncensored";
  if (CHINESE_PREFIX.test(c)) return "chinese";
  // MGStage 常见：数字开头厂牌 259LUXU-001 / SIRO- / LUXU-
  if (/^\d{2,4}[A-Z]{2,10}-\d+/i.test(c)) return "mgstage";
  if (/^(SIRO|LUXU|MAAN|GANA|ARA|NTR|DCV|MIUM|JAC|ORECO|ORE)-?\d+/i.test(c)) {
    return "mgstage";
  }
  return "av";
}

/**
 * 各类型刮削顺序（对齐 MoviePilot 风格默认优先级；封面优先）。
 * Freejavbt/7mm 易串片：仍可进链，合并片名时会跳过不可信源。
 */
export const PRIORITY_BY_KIND: Record<
  CodeKind,
  { meta: SourceId[]; cover: SourceId[] }
> = {
  // 有码番号：Dmm, Mgstage, Javlibrary, Avbase, Hbox_jp, Javdb, Javbus, Jav321, Avmoo, Mmtv, Airav_io, Freejavbt, Miss_av
  av: {
    meta: [
      "dmm",
      "mgstage",
      "javlibrary",
      "avbase",
      "hbox_jp",
      "javdb",
      "javbus",
      "jav321",
      "avmoo",
      "sevenmmtv",
      "airav_io",
      "freejavbt",
      "miss_av",
    ],
    cover: [
      "dmm",
      "mgstage",
      "javlibrary",
      "avbase",
      "hbox_jp",
      "javdb",
      "javbus",
      "jav321",
      "avmoo",
      "sevenmmtv",
      "airav_io",
      "freejavbt",
      "miss_av",
    ],
  },
  // 无码番号：Carib, Avbase, Javbus, Javdb, Avsox, Mmtv, Airav_io, Freejavbt, Miss_av
  uncensored: {
    meta: [
      "carib",
      "avbase",
      "javbus",
      "javdb",
      "avsox",
      "sevenmmtv",
      "airav_io",
      "freejavbt",
      "miss_av",
    ],
    cover: [
      "carib",
      "avbase",
      "javbus",
      "javdb",
      "avsox",
      "sevenmmtv",
      "airav_io",
      "freejavbt",
      "miss_av",
    ],
  },
  // 素人番号：Mgstage, Carib, Javlibrary, Avsox, Avmoo, Javbus, Javdb, Jav321, Mmtv, Airav_io, Freejavbt, Miss_av
  mgstage: {
    meta: [
      "mgstage",
      "carib",
      "javlibrary",
      "avsox",
      "avmoo",
      "javbus",
      "javdb",
      "jav321",
      "sevenmmtv",
      "airav_io",
      "freejavbt",
      "miss_av",
    ],
    cover: [
      "mgstage",
      "carib",
      "javlibrary",
      "avsox",
      "avmoo",
      "javbus",
      "javdb",
      "jav321",
      "sevenmmtv",
      "airav_io",
      "freejavbt",
      "miss_av",
    ],
  },
  // FC2：封面优先 fd2ppv（横版样图）；官方/Hub/airav/miss 兜底
  fc2: {
    meta: [
      "fc2",
      "fd2ppv",
      "fc2_hub",
      "javdb",
      "avsox",
      "airav",
      "airav_io",
      "sevenmmtv",
      "freejavbt",
      "miss_av",
    ],
    cover: [
      "fd2ppv",
      "fc2",
      "fc2_hub",
      "javdb",
      "avsox",
      "airav",
      "airav_io",
      "sevenmmtv",
      "freejavbt",
      "miss_av",
    ],
  },
  // 国产：Madouqu, Madou, Xiao_huang_shu, Mmtv
  chinese: {
    meta: ["madouqu", "madou", "xiao_huang_shu", "sevenmmtv"],
    cover: ["madouqu", "madou", "xiao_huang_shu", "sevenmmtv"],
  },
  // 欧美：ThePornDB
  western: {
    meta: ["theporndb"],
    cover: ["theporndb"],
  },
};

/** @deprecated 兼容旧引用；请用 getOrdersForCode */
export const TITLE_PRIORITY: SourceId[] = PRIORITY_BY_KIND.av.meta;
/** @deprecated */
export const COVER_PRIORITY: SourceId[] = PRIORITY_BY_KIND.av.cover;

export function normalizeCodeKind(
  raw: unknown,
  fallback: CodeKind = "av",
): CodeKind {
  const s = String(raw || "").trim().toLowerCase();
  if ((CODE_KINDS as string[]).includes(s)) return s as CodeKind;
  // 兼容旧「按图片/按资料」
  if (s === "cover" || s === "meta") return fallback;
  return fallback;
}

const SOURCE_ID_SET = new Set<string>(
  [
    "airav",
    "airav_io",
    "avbase",
    "avmoo",
    "avsox",
    "carib",
    "dmm",
    "fc2",
    "fc2_hub",
    "fd2ppv",
    "freejavbt",
    "hbox_jp",
    "jav321",
    "javbus",
    "javdb",
    "javlibrary",
    "madou",
    "madouqu",
    "mgstage",
    "miss_av",
    "sevenmmtv",
    "theporndb",
    "xiao_huang_shu",
  ] satisfies SourceId[],
);

function normalizeSourceList(
  raw: unknown,
  fallback: SourceId[],
): SourceId[] {
  if (!Array.isArray(raw)) return [...fallback];
  const out: SourceId[] = [];
  const seen = new Set<string>();
  for (const x of raw) {
    const id = String(x || "").trim();
    if (!SOURCE_ID_SET.has(id) || seen.has(id)) continue;
    seen.add(id);
    out.push(id as SourceId);
  }
  return out.length > 0 ? out : [...fallback];
}

/** 合并用户配置与默认优先级；缺项用默认补齐 */
export function mergePriorityByKind(raw: unknown): PriorityByKind {
  const out = {} as PriorityByKind;
  const obj =
    raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  for (const kind of CODE_KINDS) {
    const def = PRIORITY_BY_KIND[kind];
    const row = obj[kind];
    // 支持单数组（UI 一张优先级表）或 {meta,cover}
    if (Array.isArray(row)) {
      const list = normalizeSourceList(row, def.cover);
      out[kind] = { meta: [...list], cover: [...list] };
      continue;
    }
    const o =
      row && typeof row === "object" ? (row as Record<string, unknown>) : {};
    // 若只改了 cover，资料链跟随封面（默认图片模式）
    const cover = normalizeSourceList(o.cover ?? o.sources, def.cover);
    const meta = Array.isArray(o.meta)
      ? normalizeSourceList(o.meta, def.meta)
      : [...cover];
    out[kind] = { meta, cover };
  }
  return out;
}

/**
 * 按番号类型取顺序（可强制 kind）；始终封面链优先（图片模式）。
 */
export function getOrdersForCode(
  code: string,
  sources: Record<SourceId, SourceConfig>,
  opts?: {
    kind?: CodeKind;
    priorityByKind?: PriorityByKind;
  },
): {
  kind: CodeKind;
  meta: SourceId[];
  cover: SourceId[];
  primary: SourceId[];
} {
  const kind = opts?.kind
    ? normalizeCodeKind(opts.kind)
    : detectCodeKind(code);
  const table = opts?.priorityByKind || PRIORITY_BY_KIND;
  const base = table[kind] || PRIORITY_BY_KIND[kind];
  // 旧配置可能缺 airav；FC2 实测它是标题+封面最稳兜底
  const meta = rankByConnectivity(ensureKindFallbacks(kind, base.meta), sources);
  const cover = rankByConnectivity(
    ensureKindFallbacks(kind, base.cover),
    sources,
  );
  // 默认图片模式：封面链打头
  const primary = [
    ...cover,
    ...meta.filter((id) => !cover.includes(id)),
  ];
  return { kind, meta, cover, primary };
}

/** 保证关键兜底源仍在链上（不打乱用户已有顺序，仅补缺） */
function ensureKindFallbacks(kind: CodeKind, order: SourceId[]): SourceId[] {
  if (kind !== "fc2") return order;
  let out = [...order];
  if (!out.includes("fd2ppv")) {
    out = ["fd2ppv", ...out];
  }
  if (!out.includes("airav")) {
    const after = out.findIndex((id) => id === "avsox" || id === "fc2_hub");
    const at = after >= 0 ? after + 1 : Math.min(2, out.length);
    out.splice(at, 0, "airav");
  }
  return out;
}

/** error 沉底；ok/unknown 保持配置相对顺序（避免新源永远排到队尾） */
function rankByConnectivity(
  order: SourceId[],
  sources: Record<SourceId, SourceConfig>,
): SourceId[] {
  const score = (id: SourceId) => {
    const st = sources[id]?.status;
    if (st === "error") return 1;
    return 0;
  };
  return [...order].sort((a, b) => score(a) - score(b));
}

export const SOURCE_DEFS: SourceDef[] = [
  // —— AV ——（默认 URL 对齐当前可用镜像）
  { id: "javbus", name: "Javbus", defaultUrl: "https://www.javbus.com", probePath: "/", group: "av" },
  { id: "javdb", name: "Javdb", defaultUrl: "https://javdb.com", probePath: "/", group: "av" },
  { id: "dmm", name: "Dmm", defaultUrl: "https://www.dmm.co.jp", probePath: "/", group: "av" },
  { id: "airav", name: "Airav", defaultUrl: "https://www.airav.wiki", probePath: "/", group: "av" },
  { id: "airav_io", name: "Airav_io", defaultUrl: "https://airav.io/cn", probePath: "/", group: "av" },
  { id: "avsox", name: "Avsox", defaultUrl: "https://avsox.click", probePath: "/", group: "av" },
  { id: "avmoo", name: "Avmoo", defaultUrl: "https://avmoo.website", probePath: "/", group: "av" },
  { id: "jav321", name: "Jav321", defaultUrl: "https://www.jav321.com", probePath: "/", group: "av" },
  { id: "javlibrary", name: "Javlibrary", defaultUrl: "https://www.javlibrary.com/cn", probePath: "/", group: "av" },
  { id: "miss_av", name: "Miss_av", defaultUrl: "https://missav123.com", probePath: "/", group: "av" },
  { id: "avbase", name: "Avbase", defaultUrl: "https://www.avbase.net", probePath: "/", group: "av" },
  { id: "mgstage", name: "Mgstage", defaultUrl: "https://www.mgstage.com", probePath: "/", group: "av" },
  { id: "carib", name: "Carib", defaultUrl: "https://www.caribbeancom.com", probePath: "/", group: "av" },
  // —— FC2 ——
  { id: "fc2_hub", name: "Fc2_hub/Javten", defaultUrl: "https://javten.com", probePath: "/", group: "fc2" },
  { id: "fc2", name: "Fc2", defaultUrl: "https://adult.contents.fc2.com", probePath: "/", group: "fc2" },
  {
    id: "fd2ppv",
    name: "Fd2ppv",
    defaultUrl: "https://fd2ppv.cc",
    probePath: "/",
    group: "fc2",
  },
  // —— 国产 ——
  { id: "madou", name: "Madou", defaultUrl: "https://madou.club", probePath: "/", group: "chinese" },
  { id: "madouqu", name: "Madouqu", defaultUrl: "https://madouqu.com", probePath: "/", group: "chinese" },
  // —— 备选 ——
  { id: "freejavbt", name: "Freejavbt", defaultUrl: "https://freejavbt.com", probePath: "/", group: "other" },
  { id: "sevenmmtv", name: "Mmtv", defaultUrl: "https://7mmtv.sx/zh", probePath: "/", group: "other" },
  { id: "hbox_jp", name: "Hbox_jp", defaultUrl: "https://hbox.jp", probePath: "/", group: "other" },
  {
    id: "theporndb",
    name: "ThePornDB",
    defaultUrl: "https://api.theporndb.net",
    probePath: "/",
    group: "other",
  },
  {
    id: "xiao_huang_shu",
    name: "Xiao_huang_shu",
    defaultUrl: "https://xchina.co",
    probePath: "/",
    group: "other",
  },
];

/** 站默认 Cookie（对齐 MDCx / Javinizer 常见做法） */
export function defaultCookieFor(id: SourceId): string {
  if (id === "javbus") return "existmag=all; age=verified; dv=1";
  if (id === "mgstage") return "adc=1";
  return "";
}

export function normalizeProxyMode(raw: unknown): ProxyMode {
  const s = String(raw || "")
    .trim()
    .toLowerCase();
  if (s === "on" || s === "always" || s === "proxy") return "on";
  if (s === "off" || s === "never" || s === "direct") return "off";
  return "inherit";
}

/** CF 站点默认开 FlareSolverr（与 mdc-ng 一致） */
export function defaultUseFlareSolverr(id: SourceId): boolean {
  return (
    id === "javdb" ||
    id === "javlibrary" ||
    id === "miss_av" ||
    id === "fc2_hub" ||
    id === "fd2ppv"
  );
}

export function defaultSourceConfig(id: SourceId): SourceConfig {
  const def = SOURCE_DEFS.find((d) => d.id === id);
  return {
    enabled: def?.defaultEnabled !== false,
    baseUrl: "",
    cookie: defaultCookieFor(id),
    userAgent: "",
    proxyMode: "inherit",
    timeoutMs: 0,
    retry: 1,
    useFlareSolverr: defaultUseFlareSolverr(id),
    status: "unknown",
    lastCheckedAt: null,
    lastError: null,
    cooldownUntil: null,
  };
}

/** 合并单站 patch（配置读写共用） */
export function applySourcePatch(
  cur: SourceConfig,
  patch: Partial<SourceConfig> | Record<string, unknown>,
): SourceConfig {
  const p = patch as Partial<SourceConfig>;
  return {
    enabled: p.enabled !== undefined ? Boolean(p.enabled) : cur.enabled,
    baseUrl:
      p.baseUrl !== undefined ? String(p.baseUrl || "").trim() : cur.baseUrl,
    cookie:
      p.cookie !== undefined ? String(p.cookie || "").trim() : cur.cookie,
    userAgent:
      p.userAgent !== undefined
        ? String(p.userAgent || "").trim()
        : cur.userAgent,
    proxyMode:
      p.proxyMode !== undefined
        ? normalizeProxyMode(p.proxyMode)
        : cur.proxyMode,
    timeoutMs:
      p.timeoutMs !== undefined
        ? Math.max(0, Math.min(120000, Number(p.timeoutMs) || 0))
        : cur.timeoutMs,
    retry:
      p.retry !== undefined
        ? Math.max(0, Math.min(5, Number(p.retry) || 0))
        : cur.retry,
    useFlareSolverr:
      p.useFlareSolverr !== undefined
        ? Boolean(p.useFlareSolverr)
        : cur.useFlareSolverr,
    status:
      p.status === "ok" || p.status === "error" || p.status === "unknown"
        ? p.status
        : cur.status,
    lastCheckedAt:
      p.lastCheckedAt !== undefined
        ? p.lastCheckedAt
          ? String(p.lastCheckedAt)
          : null
        : cur.lastCheckedAt,
    lastError:
      p.lastError !== undefined
        ? p.lastError != null
          ? String(p.lastError)
          : null
        : cur.lastError,
    cooldownUntil:
      p.cooldownUntil !== undefined
        ? p.cooldownUntil
          ? String(p.cooldownUntil)
          : null
        : cur.cooldownUntil,
  };
}

export function defaultSourcesMap(): Record<SourceId, SourceConfig> {
  const out = {} as Record<SourceId, SourceConfig>;
  for (const def of SOURCE_DEFS) {
    out[def.id] = defaultSourceConfig(def.id);
  }
  return out;
}

export function mergeSourcesConfig(
  raw: Partial<Record<string, Partial<SourceConfig>>> | undefined,
): Record<SourceId, SourceConfig> {
  const base = defaultSourcesMap();
  if (!raw || typeof raw !== "object") return base;
  for (const def of SOURCE_DEFS) {
    const patch = raw[def.id];
    if (!patch || typeof patch !== "object") continue;
    // 旧配置缺 cookie 等字段时沿用站默认；status 探测字段单独处理
    const merged = applySourcePatch(base[def.id], patch);
    merged.status =
      patch.status === "ok" || patch.status === "error"
        ? patch.status
        : "unknown";
    merged.lastCheckedAt = patch.lastCheckedAt
      ? String(patch.lastCheckedAt)
      : null;
    merged.lastError =
      patch.lastError !== undefined && patch.lastError !== null
        ? String(patch.lastError)
        : null;
    merged.cooldownUntil = patch.cooldownUntil
      ? String(patch.cooldownUntil)
      : null;
    base[def.id] = merged;
  }
  return base;
}

export function resolveBaseUrl(id: SourceId, cfg: SourceConfig): string {
  const def = SOURCE_DEFS.find((d) => d.id === id)!;
  return (cfg.baseUrl || def.defaultUrl).trim().replace(/\/$/, "");
}

export function isSourceUsable(cfg: SourceConfig): boolean {
  if (!cfg.enabled) return false;
  if (cfg.cooldownUntil) {
    const t = Date.parse(cfg.cooldownUntil);
    if (!Number.isNaN(t) && t > Date.now()) return false;
  }
  return true;
}

export type SourceCard = {
  id: SourceId;
  name: string;
  url: string;
  enabled: boolean;
  cookie: string;
  userAgent: string;
  proxyMode: ProxyMode;
  timeoutMs: number;
  retry: number;
  useFlareSolverr: boolean;
  status: SourceStatus;
  lastCheckedAt: string | null;
  lastError: string | null;
  cooldownUntil: string | null;
  cooldownRemainingSec: number | null;
  group: SourceDef["group"];
};

export function toSourceCards(
  map: Record<SourceId, SourceConfig>,
): SourceCard[] {
  const now = Date.now();
  return SOURCE_DEFS.map((def) => {
    const cfg = map[def.id];
    let cooldownRemainingSec: number | null = null;
    if (cfg.cooldownUntil) {
      const t = Date.parse(cfg.cooldownUntil);
      if (!Number.isNaN(t) && t > now) {
        cooldownRemainingSec = Math.ceil((t - now) / 1000);
      }
    }
    return {
      id: def.id,
      name: def.name,
      url: resolveBaseUrl(def.id, cfg),
      enabled: cfg.enabled,
      cookie: cfg.cookie || "",
      userAgent: cfg.userAgent || "",
      proxyMode: cfg.proxyMode || "inherit",
      timeoutMs: cfg.timeoutMs || 0,
      retry: cfg.retry ?? 1,
      useFlareSolverr: Boolean(cfg.useFlareSolverr),
      status: cfg.status,
      lastCheckedAt: cfg.lastCheckedAt,
      lastError: cfg.lastError,
      cooldownUntil: cfg.cooldownUntil,
      cooldownRemainingSec,
      group: def.group,
    };
  });
}

/** 探测错误转中文，便于设置页展示 */
export function zhProbeError(raw: string | null | undefined): string {
  if (!raw) return "未知错误";
  const s = String(raw).trim();
  if (/^HTTP\s+(\d+)/i.test(s)) {
    return `服务器错误（${s.match(/\d+/)?.[0]}）`;
  }
  if (/timeout|aborted|TimeoutError|UND_ERR_CONNECT_TIMEOUT|HeadersTimeout/i.test(s)) {
    return "连接超时";
  }
  if (/ECONNREFUSED/i.test(s)) return "连接被拒绝";
  if (/ENOTFOUND|getaddrinfo/i.test(s)) return "域名无法解析";
  if (/ECONNRESET|socket hang up/i.test(s)) return "连接被重置";
  if (/CERT_|SSL|TLS|certificate/i.test(s)) return "证书错误";
  if (/proxy|PROXY/i.test(s)) return "代理异常";
  if (/fetch failed/i.test(s)) return "请求失败";
  if (/network/i.test(s)) return "网络异常";
  // 已是中文则原样
  if (/[\u4e00-\u9fff]/.test(s)) return s;
  return `请求失败（${s.slice(0, 80)}）`;
}

export async function probeSource(
  id: SourceId,
  cfg: SourceConfig,
): Promise<Pick<SourceConfig, "status" | "lastCheckedAt" | "lastError">> {
  const def = SOURCE_DEFS.find((d) => d.id === id)!;
  const base = resolveBaseUrl(id, cfg);
  const url = `${base}${def.probePath.startsWith("/") ? def.probePath : `/${def.probePath}`}`;
  const checkedAt = new Date().toISOString();
  try {
    const { buildSourceFetchInit } = await import("../httpContext.js");
    const init = buildSourceFetchInit(cfg, {
      method: "GET",
      timeoutMs: cfg.timeoutMs > 0 ? cfg.timeoutMs : 12000,
      accept: "text/html,*/*",
    });
    const res = await undiciFetch(url, init);
    if (res.status >= 500) {
      return {
        status: "error",
        lastCheckedAt: checkedAt,
        lastError: `服务器错误（${res.status}）`,
      };
    }
    return { status: "ok", lastCheckedAt: checkedAt, lastError: null };
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err);
    return {
      status: "error",
      lastCheckedAt: checkedAt,
      lastError: zhProbeError(raw),
    };
  }
}
