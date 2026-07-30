import { readConfig } from "./config.js";
import { normalizeCode } from "./db.js";
import {
  profileFromSource,
  runWithRequestProfile,
} from "./httpContext.js";
import { downloadCoverFromUrl } from "./sources/dmm.js";
import {
  getOrdersForCode,
  isSourceUsable,
  normalizeCodeKind,
  resolveBaseUrl,
  zhProbeError,
  type CodeKind,
  type SourceId,
} from "./sources/registry.js";
import { SOURCE_SCRAPERS } from "./sources/runners.js";
import { uniqNames, type PartialMeta } from "./sources/http.js";
import { finalizeTitleZh } from "./sources/util.js";

export type ScrapeResult = {
  code: string;
  kind?: string;
  title: string | null;
  title_zh: string | null;
  title_ja: string | null;
  actresses: string[];
  cover_path: string | null;
  cover_source: string | null;
  sources: string[];
  status: "ok" | "missing" | "error" | "skipped";
  error?: string | null;
};

/** 易串片源：其「中文片名」不可信，仅可作封面候选 */
const UNTRUSTED_TITLE_SOURCES = new Set([
  "freejavbt",
  "sevenmmtv",
]);

/** 片名里出现明显他人艺名，且不在本片女优列表 → 串片 */
function titleLooksMismatched(
  title: string,
  actresses: string[],
): boolean {
  const t = title.replace(/\s+/g, "");
  const actBlob = actresses.join("").replace(/\s+/g, "");
  // 常见艺名（可扩展）；命中且女优列表不含 → 拒
  const celebs = [
    "三上悠亞",
    "三上悠亚",
    "橋本有菜",
    "桥本有菜",
    "明日花綺羅",
    "明日花绮罗",
    "河北彩花",
    "楓可憐",
    "枫可怜",
    "相澤南",
    "相泽南",
    "篠田優",
    "篠田优",
    "深田詠美",
    "深田咏美",
  ];
  for (const name of celebs) {
    if (!t.includes(name)) continue;
    if (actBlob.includes(name)) continue;
    // 女优列表是日文名时，中文艺名对不上也算可疑
    return true;
  }
  return false;
}

function preferTitle(zh: string | null, ja: string | null): string | null {
  // 源站原文：有中文用中文，否则日文；不做机翻
  return zh || ja || null;
}

function hasTrustedTitle(parts: PartialMeta[]): boolean {
  return parts.some((p) => {
    if (UNTRUSTED_TITLE_SOURCES.has(String(p.source || ""))) return false;
    return Boolean(p.title_zh || p.title_ja);
  });
}

function hasEnough(parts: PartialMeta[], kind: string): boolean {
  const title = hasTrustedTitle(parts);
  const actress = parts.some((p) => (p.actresses?.length || 0) > 0);
  const cover = parts.some((p) => p.cover_url);
  // 片名（中/日原文）+ 封面即可早停；FC2/国产/欧美可无女优
  if (kind === "fc2" || kind === "chinese" || kind === "western")
    return Boolean(title && cover);
  return Boolean(title && actress && cover);
}

function mergeMeta(parts: PartialMeta[]): {
  title_zh: string | null;
  title_ja: string | null;
  actresses: string[];
  sources: string[];
} {
  let title_zh: string | null = null;
  let title_ja: string | null = null;
  const actresses: string[] = [];
  const sources: string[] = [];

  // 先收女优，供片名串片校验
  for (const p of parts) {
    if (p.actresses?.length) actresses.push(...p.actresses);
  }
  const actList = uniqNames(actresses);

  // 可信源优先取中文片名
  const ordered = [
    ...parts.filter((p) => !UNTRUSTED_TITLE_SOURCES.has(String(p.source || ""))),
    ...parts.filter((p) => UNTRUSTED_TITLE_SOURCES.has(String(p.source || ""))),
  ];

  for (const p of ordered) {
    if (p.source) sources.push(p.source);
    if (!title_zh && p.title_zh) {
      if (
        UNTRUSTED_TITLE_SOURCES.has(String(p.source || "")) ||
        titleLooksMismatched(p.title_zh, actList)
      ) {
        // 跳过不可信 / 串片中文名
      } else {
        title_zh = p.title_zh;
      }
    }
    if (!title_ja && p.title_ja) title_ja = p.title_ja;
  }

  if (
    !title_zh &&
    title_ja &&
    /[\u4e00-\u9fff]/.test(title_ja) &&
    !/[\u3040-\u30ff]/.test(title_ja)
  ) {
    title_zh = title_ja;
  }

  return {
    title_zh,
    title_ja,
    actresses: actList,
    sources: [...new Set(sources)],
  };
}

async function trySource(
  name: string,
  fn: () => Promise<PartialMeta>,
): Promise<PartialMeta | null> {
  try {
    const meta = await fn();
    console.log(`[scrape] ${name} ok`);
    return meta;
  } catch (err) {
    console.log(
      `[scrape] ${name} fail:`,
      err instanceof Error ? err.message : err,
    );
    return null;
  }
}

/**
 * 按番号类型分流刮削：
 * AV→AV站，FC2→FC2站，国产→国产站；
 * 同类型内连通性好的优先，挂了换下一个。
 * overwrite=true：封面强制重下，覆盖本地文件。
 */
export async function scrapeCode(
  rawCode: string,
  opts?: { overwrite?: boolean; kind?: CodeKind },
): Promise<ScrapeResult> {
  const overwrite = Boolean(opts?.overwrite);
  const code = normalizeCode(rawCode);
  if (!code) {
    return {
      code: rawCode,
      title: null,
      title_zh: null,
      title_ja: null,
      actresses: [],
      cover_path: null,
      cover_source: null,
      sources: [],
      status: "error",
      error: "番号为空",
    };
  }

  const cfg = await readConfig();
  const src = cfg.sources;
  const kindOverride =
    opts?.kind !== undefined ? normalizeCodeKind(opts.kind) : undefined;
  const {
    kind,
    cover: coverOrder,
    primary: primaryOrder,
  } = getOrdersForCode(code, src, {
    kind: kindOverride,
    priorityByKind: cfg.priorityByKind,
  });
  console.log(`[scrape] ${code} kind=${kind}`);

  const parts: PartialMeta[] = [];
  const order = primaryOrder;

  for (const id of order) {
    if (!isSourceUsable(src[id])) continue;
    const fn = SOURCE_SCRAPERS[id];
    if (!fn) continue;
    const baseUrl = resolveBaseUrl(id, src[id]);
    const meta = await trySource(id, () =>
      runWithRequestProfile(profileFromSource(src[id]), () =>
        fn(code, { baseUrl }),
      ),
    );
    if (meta) parts.push({ ...meta, source: id });
    if (hasEnough(parts, kind)) break;
  }

  const haveCover = parts.some((p) => p.cover_url);
  if (!haveCover) {
    for (const id of coverOrder) {
      if (!isSourceUsable(src[id])) continue;
      if (parts.some((p) => p.source === id)) continue;
      const fn = SOURCE_SCRAPERS[id];
      if (!fn) continue;
      const meta = await trySource(`cover:${id}`, () =>
        runWithRequestProfile(profileFromSource(src[id]), () =>
          fn(code, { baseUrl: resolveBaseUrl(id, src[id]) }),
        ),
      );
      if (meta?.cover_url) parts.push({ ...meta, source: id });
      if (parts.some((p) => p.cover_url)) break;
    }
  }

  let cover_path: string | null = null;
  let usedCoverSource: string | null = null;
  let lastCoverErr: string | null = null;

  const coverCandidates = coverOrder
    .map((id) => parts.find((p) => p.source === id && p.cover_url))
    .filter(Boolean) as PartialMeta[];
  if (!coverCandidates.length) {
    const any = parts.find((p) => p.cover_url);
    if (any) coverCandidates.push(any);
  }

  for (const hit of coverCandidates) {
    const id = (hit.source || "unknown") as SourceId;
    const srcCfg = src[id];
    const referer = srcCfg
      ? `${resolveBaseUrl(id, srcCfg)}/`
      : undefined;
    try {
      const download = () =>
        downloadCoverFromUrl(
          code,
          hit.cover_url!,
          referer || "https://www.google.com/",
          { overwrite, kind },
        );
      cover_path = srcCfg
        ? await runWithRequestProfile(profileFromSource(srcCfg), download)
        : await download();
      usedCoverSource = hit.source || null;
      lastCoverErr = null;
      break;
    } catch (err) {
      lastCoverErr = err instanceof Error ? err.message : String(err);
    }
  }

  if (!cover_path) {
    for (const id of coverOrder) {
      if (!isSourceUsable(src[id])) continue;
      const fn = SOURCE_SCRAPERS[id];
      if (!fn) continue;
      const meta = await trySource(`cover-retry:${id}`, () =>
        runWithRequestProfile(profileFromSource(src[id]), () =>
          fn(code, { baseUrl: resolveBaseUrl(id, src[id]) }),
        ),
      );
      if (!meta?.cover_url) continue;
      try {
        cover_path = await runWithRequestProfile(
          profileFromSource(src[id]),
          () =>
            downloadCoverFromUrl(
              code,
              meta.cover_url!,
              `${resolveBaseUrl(id, src[id])}/`,
              { overwrite, kind },
            ),
        );
        usedCoverSource = id;
        lastCoverErr = null;
        parts.push({ ...meta, source: id });
        break;
      } catch (err) {
        lastCoverErr = err instanceof Error ? err.message : String(err);
      }
    }
  }

  const mergedFinal = mergeMeta(parts);
  let title_zh = mergedFinal.title_zh;
  let title_ja = mergedFinal.title_ja;
  const allActresses = mergedFinal.actresses;

  if (title_ja) {
    title_ja = finalizeTitleZh(title_ja, allActresses) || title_ja;
  }
  if (title_zh) {
    title_zh = finalizeTitleZh(title_zh, allActresses) || title_zh;
  }

  const actresses = uniqNames(allActresses);
  const title = preferTitle(title_zh, title_ja);
  const ok = Boolean(cover_path) && Boolean(title);

  // 封面校验/下载失败 → error（计入队列「失败」）；纯未找到 → missing
  let status: "ok" | "missing" | "error" = "missing";
  if (ok) status = "ok";
  else if (lastCoverErr) status = "error";

  return {
    code,
    kind,
    title,
    title_zh: title_zh || null,
    title_ja: title_ja || null,
    actresses,
    cover_path,
    cover_source: cover_path ? usedCoverSource : null,
    sources: mergedFinal.sources,
    status,
    error: ok
      ? null
      : !title
        ? lastCoverErr
          ? `缺片名；封面：${zhProbeError(lastCoverErr)}`
          : "未获取到片名"
        : lastCoverErr
          ? `封面下载失败：${zhProbeError(lastCoverErr)}`
          : "未找到元数据",
  };
}
