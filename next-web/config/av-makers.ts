import japanJson from "./av-makers.japan.json";
import chinaJson from "./av-makers.china.json";
import westernJson from "./av-makers.western.json";

export type AvMakerKind = "有码" | "无码" | "国产" | "欧美";

/** 封面宽高比，如 `2/3`、`16/9`；可在 maker / prefix 级单独改 */
export type CoverAspect = string;

export type AvMakerEntry = {
  maker: string;
  kind: AvMakerKind;
  description?: string;
  prefixes: string[];
  prefix_notes?: Record<string, string>;
  /** 厂牌默认封面比例 */
  cover_aspect?: CoverAspect;
  /** 个别前缀覆盖厂牌比例 */
  prefix_aspects?: Record<string, CoverAspect>;
};

export type CoverDisplay = {
  /** CSS aspect-ratio 值，如 `16 / 9` */
  aspectRatio: string;
  /** 原始配置串，如 `16/9` */
  aspect: CoverAspect;
  preferLandscape: boolean;
  /** 有码竖图裁右侧；横图居中 */
  objectPosition: "right top" | "center";
};

export const AV_MAKERS_JAPAN = japanJson as AvMakerEntry[];
export const AV_MAKERS_CHINA = chinaJson as AvMakerEntry[];
export const AV_MAKERS_WESTERN = westernJson as AvMakerEntry[];
export const AV_MAKERS_ALL = [
  ...AV_MAKERS_JAPAN,
  ...AV_MAKERS_CHINA,
  ...AV_MAKERS_WESTERN,
];

const byMaker = new Map(
  AV_MAKERS_ALL.map((m) => [m.maker.trim().toLowerCase(), m]),
);

const byPrefix = new Map<string, AvMakerEntry>();
for (const m of AV_MAKERS_ALL) {
  for (const p of m.prefixes || []) {
    const key = String(p || "")
      .trim()
      .toUpperCase()
      .replace(/_/g, "-");
    if (key && !byPrefix.has(key)) byPrefix.set(key, m);
  }
}

export function findMakerMeta(maker: string): AvMakerEntry | undefined {
  const key = (maker || "").trim().toLowerCase();
  if (!key) return undefined;
  return byMaker.get(key);
}

export function findMakerByPrefix(prefix: string): AvMakerEntry | undefined {
  const key = String(prefix || "")
    .trim()
    .toUpperCase()
    .replace(/_/g, "-");
  if (!key) return undefined;
  return byPrefix.get(key);
}

export function makerDescription(maker: string): string {
  return findMakerMeta(maker)?.description?.trim() || "";
}

export function prefixNote(maker: string, prefix: string): string {
  const meta = findMakerMeta(maker);
  if (!meta?.prefix_notes) return "";
  const code = (prefix || "").trim();
  if (!code) return "";
  return (
    meta.prefix_notes[code]?.trim() ||
    meta.prefix_notes[code.toUpperCase()]?.trim() ||
    ""
  );
}

function normalizeAspect(
  raw: string | undefined,
  fallback: CoverAspect,
): CoverAspect {
  const s = String(raw || "")
    .trim()
    .replace(/\s+/g, "")
    .replace(":", "/");
  if (!/^\d+(\.\d+)?\/\d+(\.\d+)?$/.test(s)) return fallback;
  return s;
}

function aspectToCss(aspect: CoverAspect): string {
  const [w, h] = aspect.split("/");
  return `${w} / ${h}`;
}

function isLandscapeAspect(aspect: CoverAspect): boolean {
  const [w, h] = aspect.split("/").map(Number);
  return Number.isFinite(w) && Number.isFinite(h) && w > h;
}

/** 由比例串生成展示参数 */
export function coverDisplayFromAspect(
  raw: CoverAspect,
  fallback: CoverAspect = "2/3",
): CoverDisplay {
  const aspect = normalizeAspect(raw, fallback);
  const preferLandscape = isLandscapeAspect(aspect);
  return {
    aspect,
    aspectRatio: aspectToCss(aspect),
    preferLandscape,
    objectPosition: preferLandscape ? "center" : "right top",
  };
}

/**
 * 按前缀解析封面展示比例（厂牌 cover_aspect + prefix_aspects 覆盖）。
 * 未配置时：无码/国产/欧美 16/9，有码 2/3。
 */
export function resolveCoverDisplay(prefix: string): CoverDisplay {
  const meta = findMakerByPrefix(prefix);
  const code = String(prefix || "")
    .trim()
    .toUpperCase()
    .replace(/_/g, "-");
  const kindFallback: CoverAspect =
    meta?.kind === "无码" ||
    meta?.kind === "国产" ||
    meta?.kind === "欧美"
      ? "16/9"
      : "2/3";
  let fromPrefix: string | undefined;
  if (meta?.prefix_aspects) {
    for (const [k, v] of Object.entries(meta.prefix_aspects)) {
      if (k.toUpperCase().replace(/_/g, "-") === code) {
        fromPrefix = v;
        break;
      }
    }
  }
  return coverDisplayFromAspect(
    fromPrefix || meta?.cover_aspect || kindFallback,
    kindFallback,
  );
}
