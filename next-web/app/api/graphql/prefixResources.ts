import { query } from "@/lib/pgdb";
import { filterPreviewImages } from "@/utils/resource";
import { loadPrefixCodesCached } from "@/lib/prefixCodeCache";
import { coverHostPriority, landscapeUrlHint } from "@/lib/imageProxy";
import { resolveCoverUrl } from "@/lib/coverUrl";
import { compareCodes, extractCodesForPrefix, isWesternStudioPrefix } from "@/utils/av-code";
import { PUBLIC_RESOURCE_FILTER } from "./resourceFilters";

export type PrefixCodeHit = {
  code: string;
  count: number;
  sampleTitle: string | null;
  sampleHash: string | null;
};

/** 单次扫描行上限；只取 filename，配合进程缓存 */
const PREFIX_SCAN_ROW_CAP = 20000;

function escapeLikePattern(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/%/g, "\\%").replace(/_/g, "\\_");
}

/** 封面优先级：色花堂图床 > 普通 > DMM/imagetwist；FC2 再偏横图 URL */
function coverRank(
  url: string | null | undefined,
  opts?: { preferLandscape?: boolean },
): number {
  let score = coverHostPriority(url) * 10;
  if (opts?.preferLandscape && url) {
    score += landscapeUrlHint(url);
  }
  return score;
}

function isFc2Prefix(prefix: string): boolean {
  const p = String(prefix || "").trim().toUpperCase();
  return p === "FC2" || p === "FC2PPV";
}

/** 前缀预筛 LIKE：常规 PREFIX-%；FC2 / FC2PPV / 欧美厂牌分入口 */
function prefixLikePatterns(prefix: string): string[] {
  const raw = String(prefix || "").trim();
  const pUpper = raw.toUpperCase();
  if (!raw) return [];

  if (pUpper === "FC2PPV") {
    return [
      "FC2PPV%",
      "%FC2PPV%",
      "%FC2-PPV%",
      "%FC2 PPV%",
      "FC2-PPV%",
      "FC2 PPV%",
    ];
  }
  if (pUpper === "FC2") {
    // 仅非 PPV：FC2-123 / FC2 123；不含 FC2PPV
    return ["FC2-%", "%FC2-%", "FC2 %", "%FC2 %"];
  }

  const esc = escapeLikePattern(raw);
  if (isWesternStudioPrefix(raw)) {
    // 欧美文件名多为 Studio.日期.标题，不全是 Studio-
    return [
      `${esc}%`,
      `%${esc}%`,
      `%${esc}.%`,
      `%${esc}-%`,
      `%${esc}_%`,
    ];
  }

  return [`${esc}-%`, `%${esc}-%`];
}

/** FC2 / Blacked 等入口排除易撞车形态 */
function prefixExcludeLikePatterns(prefix: string): string[] {
  const p = String(prefix || "").trim().toUpperCase();
  if (p === "FC2") {
    return [
      "%FC2PPV%",
      "FC2PPV%",
      "%FC2-PPV%",
      "FC2-PPV%",
      "%FC2 PPV%",
      "FC2 PPV%",
    ];
  }
  if (p === "BLACKED") {
    return ["%BlackedRaw%", "%BLACKEDRAW%", "%blackedraw%"];
  }
  return [];
}

function pickRankedCovers(
  images?: string[] | null,
  limit = 6,
  opts?: { preferLandscape?: boolean },
): string[] {
  const list = filterPreviewImages(images);
  if (!list.length) return [];
  return [...list]
    .sort((a, b) => coverRank(b, opts) - coverRank(a, opts))
    .slice(0, limit);
}

function mergeCoverUrls(
  prev: string[] | undefined,
  next: string[],
  opts?: { preferLandscape?: boolean },
): string[] {
  const map = new Map<string, string>();
  for (const u of [...(prev || []), ...next]) {
    if (u) map.set(u, u);
  }
  return Array.from(map.values())
    .sort((a, b) => coverRank(b, opts) - coverRank(a, opts))
    .slice(0, 6);
}

/** 刮削封面优先插入；每次列表请求都跑，避免前缀缓存卡住旧封面 */
async function applyAvMetadataCovers(
  items: Array<{ code: string; coverUrl: string | null; coverUrls: string[] }>,
) {
  const codes = items.map((it) => it.code);
  if (!codes.length) return;
  try {
    const { rows: metaRows } = await query(
      `SELECT code, cover_path
       FROM av_metadata
       WHERE status = 'ok'
         AND coalesce(cover_path, '') <> ''
         AND code = ANY($1)`,
      [codes],
    );
    const metaMap = new Map(
      metaRows.map((r) => [
        r.code,
        resolveCoverUrl(r.cover_path) || r.cover_path,
      ]),
    );
    for (const it of items) {
      const metaCover = metaMap.get(it.code);
      if (!metaCover) continue;
      it.coverUrls = [
        metaCover,
        ...it.coverUrls.filter((u) => u !== metaCover),
      ].slice(0, 6);
      it.coverUrl = it.coverUrls[0] || null;
    }
  } catch (err) {
    console.warn("av_metadata lookup skipped:", err);
  }
}

/**
 * 轻量扫描：filename + 预览图，去重排序后进缓存。
 * 同番号多资源：收集多封面候选（优先稳定图床）。
 * 番号集合可缓存；封面在返回前用 av_metadata 刷新（刮削后立即生效）。
 */
async function scanPrefixCodeIndex(prefix: string): Promise<{
  items: Array<{ code: string; coverUrl: string | null; coverUrls: string[] }>;
  matchedRows: number;
}> {
  const needle = String(prefix || "").trim();
  if (!needle) return { items: [], matchedRows: 0 };

  const indexed = await loadPrefixCodesCached(needle, async () => {
    const likes = prefixLikePatterns(needle);
    if (!likes.length) return { items: [], matchedRows: 0 };
    const excludes = prefixExcludeLikePatterns(needle);
const landscapeOpts =
      isFc2Prefix(needle) || isWesternStudioPrefix(needle)
        ? { preferLandscape: true }
        : undefined;
    // filename 常无番号、title 有（尤其 FC2PPV-xxxxxx）；两边都扫
    const excludeSql = excludes.length
      ? `
  AND NOT EXISTS (
    SELECT 1
    FROM unnest($3::text[]) AS e(pat)
    WHERE COALESCE(r.filename, '') ILIKE e.pat
       OR COALESCE(rs.title, '') ILIKE e.pat
  )`
      : "";
    const sql = `
SELECT
  r.filename,
  rs.title,
  rs.preview_images
FROM ed2k_resources r
LEFT JOIN LATERAL (
  SELECT title, preview_images
  FROM resource_sources
  WHERE hash = r.hash
  ORDER BY coalesce(array_length(preview_images, 1), 0) DESC, created_at DESC
  LIMIT 1
) rs ON true
WHERE TRUE
${PUBLIC_RESOURCE_FILTER}
  AND EXISTS (
    SELECT 1
    FROM unnest($1::text[]) AS p(pat)
    WHERE COALESCE(r.filename, '') ILIKE p.pat
       OR COALESCE(rs.title, '') ILIKE p.pat
  )
${excludeSql}
ORDER BY
  CASE WHEN coalesce(array_length(rs.preview_images, 1), 0) > 0 THEN 0 ELSE 1 END
LIMIT $2
`;
    const params: unknown[] = [likes, PREFIX_SCAN_ROW_CAP];
    if (excludes.length) params.push(excludes);
    const { rows } = await query(sql, params);
    const map = new Map<
      string,
      { code: string; coverUrl: string | null; coverUrls: string[] }
    >();

    for (const row of rows as Array<{
      filename: string | null;
      title?: string | null;
      preview_images?: string[] | null;
    }>) {
      const blob = [row.filename, row.title].filter(Boolean).join("\n");
      if (!blob) continue;
      const covers = pickRankedCovers(row.preview_images, 2, landscapeOpts);
      for (const code of extractCodesForPrefix(blob, needle)) {
        const prev = map.get(code);
        if (!prev) {
          map.set(code, {
            code,
            coverUrl: covers[0] || null,
            coverUrls: covers,
          });
        } else {
          const merged = mergeCoverUrls(prev.coverUrls, covers, landscapeOpts);
          prev.coverUrls = merged;
          prev.coverUrl = merged[0] || null;
        }
      }
    }

    const items = Array.from(map.values()).sort((a, b) =>
      compareCodes(a.code, b.code),
    );

    return { items, matchedRows: rows.length };
  });

  // 浅拷贝后返回；av_metadata 封面在分页切片上合并，避免整表拖慢首屏
  const items = indexed.items.map((it) => ({
    ...it,
    coverUrls: [...it.coverUrls],
  }));
  return { items, matchedRows: indexed.matchedRows };
}

/** 按前缀扫描库内文件名，汇总已有番号编号（升序） */
export async function listPrefixCodes(
  prefix: string,
  {
    limit = 200,
    offset = 0,
  }: {
    limit?: number;
    offset?: number;
  } = {},
): Promise<{
  codes: PrefixCodeHit[];
  total_codes: number;
  matched_rows: number;
}> {
  const needle = String(prefix || "").trim();
  if (!needle) {
    return { codes: [], total_codes: 0, matched_rows: 0 };
  }

  const safeLimit = Math.min(Math.max(Number(limit) || 200, 1), 2000);
  const safeOffset = Math.max(Number(offset) || 0, 0);

  try {
    const { items, matchedRows } = await scanPrefixCodeIndex(needle);
    return {
      codes: items.slice(safeOffset, safeOffset + safeLimit).map((it) => ({
        code: it.code,
        count: 1,
        sampleTitle: null,
        sampleHash: null,
      })),
      total_codes: items.length,
      matched_rows: matchedRows,
    };
  } catch (error) {
    console.error("Error in listPrefixCodes:", error);
    throw new Error(
      `Failed to list prefix codes: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

export type PrefixResourceHit = {
  code: string;
  coverUrl: string | null;
  coverUrls: string[];
};

/** 按前缀列出库内番号，按数字升序（001 → 002 → …）；结果缓存后分页 */
export async function listPrefixResources(
  prefix: string,
  {
    limit = 60,
    offset = 0,
  }: {
    limit?: number;
    offset?: number;
  } = {},
): Promise<{
  items: PrefixResourceHit[];
  total_count: number;
  matched_rows: number;
}> {
  const needle = String(prefix || "").trim();
  if (!needle) {
    return { items: [], total_count: 0, matched_rows: 0 };
  }

  const safeLimit = Math.min(Math.max(Number(limit) || 60, 1), 200);
  const safeOffset = Math.max(Number(offset) || 0, 0);

  try {
    const { items, matchedRows } = await scanPrefixCodeIndex(needle);
    const page = items
      .slice(safeOffset, safeOffset + safeLimit)
      .map((it) => ({
        ...it,
        coverUrls: [...it.coverUrls],
      }));
    await applyAvMetadataCovers(page);
    return {
      items: page,
      total_count: items.length,
      matched_rows: matchedRows,
    };
  } catch (error) {
    console.error("Error in listPrefixResources:", error);
    throw new Error(
      `Failed to list prefix resources: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

/** 按女优名在 av_metadata 中查番号（封面卡片用） */
export async function listActressResources(
  name: string,
  {
    limit = 60,
    offset = 0,
  }: {
    limit?: number;
    offset?: number;
  } = {},
): Promise<{
  items: PrefixResourceHit[];
  total_count: number;
}> {
  const needle = String(name || "").trim();
  if (!needle) {
    return { items: [], total_count: 0 };
  }

  const safeLimit = Math.min(Math.max(Number(limit) || 60, 1), 200);
  const safeOffset = Math.max(Number(offset) || 0, 0);
  const like = `%${escapeLikePattern(needle)}%`;

  try {
    const countRes = await query(
      `SELECT COUNT(*)::text AS n
       FROM av_metadata m
       WHERE m.status = 'ok'
         AND EXISTS (
           SELECT 1
           FROM unnest(COALESCE(m.actresses, '{}'::text[])) AS a(name)
           WHERE a.name ILIKE $1 ESCAPE '\\'
         )`,
      [like],
    );
    const total_count = Number(countRes.rows[0]?.n || 0) || 0;
    if (!total_count) {
      return { items: [], total_count: 0 };
    }

    const { rows } = await query(
      `SELECT m.code, m.cover_path
       FROM av_metadata m
       WHERE m.status = 'ok'
         AND EXISTS (
           SELECT 1
           FROM unnest(COALESCE(m.actresses, '{}'::text[])) AS a(name)
           WHERE a.name ILIKE $1 ESCAPE '\\'
         )
       ORDER BY
         CASE WHEN coalesce(m.cover_path, '') <> '' THEN 0 ELSE 1 END,
         m.code ASC
       LIMIT $2 OFFSET $3`,
      [like, safeLimit, safeOffset],
    );

    const items: PrefixResourceHit[] = rows.map((r) => {
      const cover = resolveCoverUrl(r.cover_path) || r.cover_path || null;
      return {
        code: r.code,
        coverUrl: cover,
        coverUrls: cover ? [cover] : [],
      };
    });

    return { items, total_count };
  } catch (error) {
    console.error("Error in listActressResources:", error);
    throw new Error(
      `Failed to list actress resources: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

/**
 * 各厂牌前缀取一张样例刮削封面。
 * 优先取该前缀编号靠前、且确有本地 cover_path 的番号（真正刮削海报）。
 */
export async function getPrefixSampleCovers(
  prefixes: string[],
): Promise<Record<string, { code: string; coverUrl: string }>> {
  const unique = Array.from(
    new Set(
      prefixes
        .map((p) => String(p || "").trim().toUpperCase())
        .filter(Boolean),
    ),
  );
  if (!unique.length) return {};

  try {
    const { rows } = await query(
      `SELECT p.prefix, m.code, m.cover_path
       FROM unnest($1::text[]) AS p(prefix)
       LEFT JOIN LATERAL (
         SELECT code, cover_path
         FROM av_metadata
         WHERE status = 'ok'
           AND coalesce(cover_path, '') <> ''
           AND cover_path LIKE '/covers/%'
           AND code ILIKE (p.prefix || '-%')
           AND code ~ ('^' || p.prefix || '-[0-9]+$')
         ORDER BY
           -- 编号升序：SSIS-001 优先于 SSIS-959，更贴系列代表作
           NULLIF(substring(code from '[0-9]+$'), '')::int ASC NULLS LAST,
           code ASC
         LIMIT 1
       ) m ON true
       WHERE m.cover_path IS NOT NULL`,
      [unique],
    );

    const out: Record<string, { code: string; coverUrl: string }> = {};
    for (const r of rows) {
      const key = String(r.prefix || "").toUpperCase();
      const cover = encodeLocalCoverPath(
        resolveCoverUrl(r.cover_path) || r.cover_path,
      );
      if (!key || !cover) continue;
      out[key] = { code: r.code, coverUrl: cover };
    }
    return out;
  } catch (err) {
    console.warn("getPrefixSampleCovers skipped:", err);
    return {};
  }
}

/** 编码 /covers/有码/... 中的非 ASCII 段，避免浏览器路径错乱 */
function encodeLocalCoverPath(url: string | null | undefined): string | null {
  if (!url) return null;
  if (!url.startsWith("/covers/")) return url;
  const rest = url.slice("/covers/".length);
  return (
    "/covers/" +
    rest
      .split("/")
      .map((seg) => {
        try {
          return encodeURIComponent(decodeURIComponent(seg));
        } catch {
          return encodeURIComponent(seg);
        }
      })
      .join("/")
  );
}

