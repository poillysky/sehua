import { query } from "@/lib/pgdb";
import { jiebaCut } from "@/lib/jieba";
import {
  MatchMode,
  SEARCH_KEYWORD_SPLIT_REGEX,
  normalizeMatchMode,
  normalizeSortType,
  resolveSortTypeForQuery,
} from "@/config/constant";
import {
  filterPreviewImages,
  isPublicDownloadLink,
  linkKindOf,
  linksForResourceHash,
  parseEd2kLink,
  RESOURCE_HASH_REGEX,
} from "@/utils/resource";

/** 公开可见：磁力 / 电驴 / 115分享 / 占位 stub */
const PUBLIC_RESOURCE_FILTER = `
  AND (
    lower(COALESCE(r.ed2k_link, '')) LIKE 'ed2k://%'
    OR lower(COALESCE(r.ed2k_link, '')) LIKE 'magnet:%'
    OR lower(COALESCE(r.ed2k_link, '')) LIKE '%115cdn.com/s/%'
    OR lower(COALESCE(r.ed2k_link, '')) LIKE '%115.com/s/%'
    OR lower(COALESCE(r.ed2k_link, '')) LIKE 'unavailable://%'
  )
`;

type Ed2kRow = {
  hash: string;
  filename: string;
  size: string;
  ed2k_link: string;
  extension: string | null;
  created_at: Date | string;
  updated_at: Date | string;
  title?: string | null;
  description?: string | null;
  source_url?: string | null;
  board_fid?: string | null;
  board_name?: string | null;
  forum_id?: string | null;
  preview_images?: string[] | null;
  ed2k_links?: string[] | null;
  extract_password?: string | null;
};

const FORUM_DISPLAY_NAMES: Record<string, string> = {
  sehuatang: "色花堂",
  other: "其他论坛",
};

function resolveForumName(forumId?: string | null, description?: string | null): string | null {
  const fid = (forumId || "").trim();
  if (fid && FORUM_DISPLAY_NAMES[fid]) return FORUM_DISPLAY_NAMES[fid];
  if (fid) return fid;
  const text = description || "";
  for (const marker of ["来源论坛名：", "来源论坛名:"]) {
    if (text.includes(marker)) {
      const line = text.split(marker, 2)[1]?.split(/\r?\n/, 1)[0]?.trim();
      if (line) return line;
    }
  }
  return null;
}

const SOURCE_META_JOIN = `
LEFT JOIN LATERAL (
  SELECT title, description, source_url, board_fid, board_name, forum_id,
         preview_images, ed2k_links, extract_password
  FROM resource_sources
  WHERE hash = r.hash
  ORDER BY
    -- 优先单链行（多链多为合集旧残留），再看预览/描述完整度
    CASE WHEN coalesce(array_length(ed2k_links, 1), 0) <= 1 THEN 0 ELSE 1 END,
    coalesce(array_length(preview_images, 1), 0) DESC,
    length(coalesce(description, '')) DESC,
    length(coalesce(title, '')) DESC,
    created_at DESC
  LIMIT 1
) rs ON true
`;

const LIST_META_JOIN = `
LEFT JOIN LATERAL (
  SELECT title, description, source_url, board_fid, board_name, forum_id,
         preview_images, ed2k_links, extract_password
  FROM resource_sources
  WHERE hash = r.hash
  ORDER BY
    CASE WHEN coalesce(array_length(ed2k_links, 1), 0) <= 1 THEN 0 ELSE 1 END,
    created_at DESC
  LIMIT 1
) rs ON true
`;

const RESOURCE_SELECT = `
  r.hash,
  r.filename,
  r.size::text,
  r.ed2k_link,
  r.extension,
  r.created_at,
  r.updated_at,
  rs.title,
  rs.description,
  rs.source_url,
  rs.board_fid,
  rs.board_name,
  rs.forum_id,
  rs.preview_images,
  rs.ed2k_links,
  rs.extract_password
`;

const LIST_RESOURCE_SELECT = `
  r.hash,
  r.filename,
  r.size::text,
  r.ed2k_link,
  r.extension,
  r.created_at,
  r.updated_at,
  rs.title,
  rs.description,
  rs.source_url,
  rs.board_fid,
  rs.board_name,
  rs.forum_id,
  rs.preview_images,
  rs.ed2k_links,
  rs.extract_password
`;

const FUZZY_STOPWORDS = new Set([
  "的",
  "了",
  "和",
  "与",
  "之",
  "在",
  "是",
  "the",
  "a",
  "an",
  "of",
  "and",
  "or",
]);

const QUOTED_KEYWORD_REGEX = /"([^"]+)"/g;

function toEpochSeconds(value: Date | string | number) {
  if (typeof value === "number") {
    return value > 1_000_000_000_000
      ? Math.floor(value / 1000)
      : Math.floor(value);
  }

  return Math.floor(new Date(value).getTime() / 1000);
}

function getExtension(filename: string, extension?: string | null) {
  if (extension) {
    return extension;
  }

  const parts = filename.split(".");

  return parts.length > 1 ? parts.pop() || "" : "";
}

export function formatResource(row: Ed2kRow) {
  const title = row.title?.trim() || null;
  const description = row.description?.trim() || null;
  const previewImages = filterPreviewImages(
    Array.isArray(row.preview_images) ? row.preview_images : [],
  );
  const rawLink = (row.ed2k_link || "").trim();
  const isStub = rawLink.toLowerCase().startsWith("unavailable://");
  // 子资源以本 hash 的 r.ed2k_link 为准，过滤合集残留在 rs.ed2k_links 里的其它磁链
  const ed2kLinks = linksForResourceHash(row.hash, row.ed2k_links, rawLink);
  const primary =
    (isPublicDownloadLink(rawLink) &&
    ed2kLinks.some((l) => l === rawLink)
      ? rawLink
      : "") ||
    ed2kLinks[0] ||
    (isStub ? rawLink : "");
  const parsedFiles = ed2kLinks.map((link, index) => {
    const parsed = parseEd2kLink(link);

    return {
      index: index + 1,
      path: parsed?.filename || row.filename,
      size: Number(parsed?.size || row.size || 0),
      extension: getExtension(parsed?.filename || row.filename, row.extension),
    };
  });
  const totalSize = parsedFiles.reduce((sum, file) => sum + Number(file.size || 0), 0);
  const displaySize = ed2kLinks.length > 1 ? totalSize : Number(row.size || 0);
  const rawBoard = row.board_name?.trim() || "";
  const boardName = rawBoard
    ? rawBoard.includes(" · ")
      ? rawBoard
      : rawBoard.includes("-")
        ? rawBoard.replace("-", " · ")
        : rawBoard
    : null;

  return {
    hash: row.hash.toUpperCase(),
    name: row.filename,
    title,
    description,
    source_url: row.source_url || null,
    board_fid: row.board_fid || null,
    board_name: boardName,
    forum_id: row.forum_id || null,
    forum_name: resolveForumName(row.forum_id, description),
    extract_password: row.extract_password?.trim() || null,
    preview_images: previewImages,
    ed2k_links: ed2kLinks,
    size: displaySize,
    ed2k_link: primary,
    link_kind: linkKindOf(primary),
    single_file: ed2kLinks.length <= 1,
    files_count: ed2kLinks.length,
    files: parsedFiles,
    created_at: toEpochSeconds(row.created_at),
    updated_at: toEpochSeconds(row.updated_at),
  };
}

const splitChineseBigrams = (text: string) => {
  const chars = text.match(/[\u4e00-\u9fff]/g) || [];
  const bigrams: { keyword: string; required: boolean }[] = [];

  for (let i = 0; i < chars.length - 1; i++) {
    bigrams.push({ keyword: `${chars[i]}${chars[i + 1]}`, required: false });
  }

  return bigrams;
};

const extractKeywords = (
  keyword: string,
  matchMode: MatchMode = "smart",
): { keyword: string; required: boolean }[] => {
  let keywords: { keyword: string; required: boolean }[] = [];
  let match;

  while ((match = QUOTED_KEYWORD_REGEX.exec(keyword)) !== null) {
    keywords.push({ keyword: match[1], required: true });
  }

  const remainingKeywords = keyword.replace(QUOTED_KEYWORD_REGEX, "");
  const plainKeyword = remainingKeywords.trim();

  keywords.push(
    ...plainKeyword
      .split(SEARCH_KEYWORD_SPLIT_REGEX)
      .filter(Boolean)
      .map((k) => ({ keyword: k, required: matchMode === "exact" })),
  );

  if (matchMode === "fuzzy" && plainKeyword.length >= 2) {
    keywords.push(...jiebaCut(plainKeyword));
  } else if (
    matchMode === "smart" &&
    keywords.length === 1 &&
    plainKeyword.length >= 4
  ) {
    keywords.push(...jiebaCut(plainKeyword));
  }

  if (matchMode === "fuzzy" && plainKeyword.length >= 4) {
    keywords.push(...splitChineseBigrams(plainKeyword));
  }

  keywords = Array.from(
    new Map(
      keywords
        .map((item) => ({
          keyword: item.keyword.trim(),
          required: item.required,
        }))
        .filter(({ keyword: itemKeyword }) =>
          itemKeyword.length >= (matchMode === "fuzzy" ? 1 : 2),
        )
        .filter(
          ({ keyword: itemKeyword }) =>
            !FUZZY_STOPWORDS.has(itemKeyword.toLowerCase()),
        )
        .map((item) => [item.keyword, item] as const),
    ).values(),
  );

  if (matchMode === "fuzzy") {
    return keywords.length
      ? keywords
      : [{ keyword: plainKeyword || keyword, required: false }];
  }

  if (matchMode === "exact") {
    return keywords.length
      ? keywords.map((item) => ({ ...item, required: true }))
      : [{ keyword: plainKeyword || keyword, required: true }];
  }

  if (keywords.length && !keywords.some(({ required }) => required)) {
    [...keywords]
      .sort((a, b) => b.keyword.length - a.keyword.length)
      .slice(0, Math.ceil(keywords.length / 3))
      .forEach((k) => (k.required = true));
  }

  const fullKeyword = keyword.replace(/"/g, "");

  if (!keywords.some((k) => k.keyword === fullKeyword)) {
    keywords.unshift({ keyword: fullKeyword, required: false });
  }

  return keywords;
};

const buildKeywordFilter = (
  keywords: { keyword: string; required: boolean }[],
  matchMode: MatchMode,
  fullKeywordParamIndex?: number,
) => {
  if (!keywords.length) {
    return "FALSE";
  }

  if (matchMode === "exact") {
    return keywords
      .map((_, i) => `(filename ILIKE $${i + 1} OR search_string ILIKE $${i + 1})`)
      .join(" AND ");
  }

  if (matchMode === "fuzzy") {
    const matchParts = keywords.map(
      (_, i) =>
        `(CASE WHEN filename ILIKE $${i + 1} OR search_string ILIKE $${i + 1} THEN 1 ELSE 0 END)`,
    );
    const matchCountExpr = matchParts.join(" + ");
    const minMatches = Math.max(1, Math.ceil(keywords.length * 0.5));
    const tokenMatch = `(${matchCountExpr}) >= ${minMatches}`;

    if (fullKeywordParamIndex) {
      const fullKeywordRef = `$${fullKeywordParamIndex}`;

      return `(${tokenMatch} OR word_similarity(${fullKeywordRef}, filename) > 0.25 OR similarity(filename, ${fullKeywordRef}) > 0.15)`;
    }

    if (keywords.length === 1) {
      return "(filename ILIKE $1 OR search_string ILIKE $1)";
    }

    return tokenMatch;
  }

  const requiredKeywords: string[] = [];
  const optionalKeywords: string[] = [];

  keywords.forEach(({ required }, i) => {
    const condition = `(filename ILIKE $${i + 1} OR search_string ILIKE $${i + 1})`;

    if (required) {
      requiredKeywords.push(condition);
    } else {
      optionalKeywords.push(condition);
    }
  });

  const fullConditions = [...requiredKeywords];

  if (optionalKeywords.length > 0) {
    optionalKeywords.push("TRUE");
    fullConditions.push(`(${optionalKeywords.join(" OR ")})`);
  }

  return fullConditions.join(" AND ");
};

const buildRelevanceOrderBy = (
  keywords: { keyword: string; required: boolean }[],
  fullKeywordParamIndex: number,
) => {
  const scoreParts = keywords.map(({ required }, i) => {
    const weight = i === 0 ? 10 : required ? 3 : 1;

    return `(CASE WHEN filename ILIKE $${i + 1} OR search_string ILIKE $${i + 1} THEN ${weight} ELSE 0 END)`;
  });

  const fullKeywordRef = `$${fullKeywordParamIndex}`;

  return `(${[
    ...scoreParts,
    `(CASE WHEN lower(filename) = lower(${fullKeywordRef}) THEN 100 ELSE 0 END)`,
    `(CASE WHEN lower(filename) LIKE lower(${fullKeywordRef}) || '%' THEN 40 ELSE 0 END)`,
    `(COALESCE(word_similarity(${fullKeywordRef}, filename), 0) * 60 + COALESCE(similarity(filename, ${fullKeywordRef}), 0) * 40)`,
  ].join(" + ")}) DESC, size DESC, created_at DESC`;
};

const buildOrderBy = (
  sortType: string,
  keywords: { keyword: string; required: boolean }[],
  fullKeywordParamIndex?: number,
) => {
  const orderByMap: Record<string, string> = {
    relevance: buildRelevanceOrderBy(
      keywords,
      fullKeywordParamIndex ?? keywords.length + 1,
    ),
    default: "created_at DESC",
    size: "size DESC, created_at DESC",
    count: "created_at DESC",
    date: "created_at DESC",
  };

  return orderByMap[sortType] || orderByMap.default;
};

const buildTimeFilter = (filterTime: string) => {
  const timeFilterMap: Record<string, string> = {
    "gt-1day": "AND created_at > now() - interval '1 day'",
    "gt-7day": "AND created_at > now() - interval '1 week'",
    "gt-31day": "AND created_at > now() - interval '1 month'",
    "gt-365day": "AND created_at > now() - interval '1 year'",
  };

  return timeFilterMap[filterTime] || "";
};

const buildSizeFilter = (filterSize: string) => {
  const sizeFilterMap: Record<string, string> = {
    lt100mb: "AND size < 100 * 1024 * 1024::bigint",
    "gt100mb-lt500mb":
      "AND size BETWEEN 100 * 1024 * 1024::bigint AND 500 * 1024 * 1024::bigint",
    "gt500mb-lt1gb":
      "AND size BETWEEN 500 * 1024 * 1024::bigint AND 1024 * 1024 * 1024::bigint",
    "gt1gb-lt5gb":
      "AND size BETWEEN 1 * 1024 * 1024 * 1024::bigint AND 5 * 1024 * 1024 * 1024::bigint",
    gt5gb: "AND size > 5 * 1024 * 1024 * 1024::bigint",
  };

  return sizeFilterMap[filterSize] || "";
};

export async function search(_: unknown, { queryInput }: any) {
  try {
    queryInput.keyword = queryInput.keyword.trim();

    const noResult = {
      keywords: [queryInput.keyword],
      resources: [],
      total_count: 0,
      has_more: false,
    };

    if (queryInput.keyword.length < 2) {
      return noResult;
    }

    if (RESOURCE_HASH_REGEX.test(queryInput.keyword)) {
      const resource = await resourceByHash(_, {
        hash: queryInput.keyword.toUpperCase(),
      });

      if (resource) {
        return {
          keywords: [queryInput.keyword],
          resources: [resource],
          total_count: 1,
          has_more: false,
        };
      }

      return noResult;
    }

    const timeFilter = buildTimeFilter(queryInput.filterTime);
    const sizeFilter = buildSizeFilter(queryInput.filterSize);
    const matchMode = normalizeMatchMode({
      matchMode: queryInput.matchMode,
      fuzzy: queryInput.fuzzy,
    });
    const sortType = resolveSortTypeForQuery(
      normalizeSortType(queryInput.sortType),
    );
    const keywords = extractKeywords(queryInput.keyword, matchMode);
    const fullKeywordPlain = queryInput.keyword.replace(/"/g, "").trim();
    const scoringExtraParams =
      matchMode === "fuzzy" || sortType === "relevance"
        ? [fullKeywordPlain]
        : [];
    const fullKeywordParamIndex = keywords.length + 1;
    const limitParamIndex = keywords.length + scoringExtraParams.length + 1;
    const offsetParamIndex = keywords.length + scoringExtraParams.length + 2;
    const orderBy = buildOrderBy(
      sortType,
      keywords,
      scoringExtraParams.length ? fullKeywordParamIndex : undefined,
    );
    const keywordFilter = buildKeywordFilter(
      keywords,
      matchMode,
      matchMode === "fuzzy" ? fullKeywordParamIndex : undefined,
    );
    const keywordsParams = keywords.map(({ keyword }) => `%${keyword}%`);
    const keywordsPlain = keywords.map(({ keyword }) => keyword);

    const sql = `
SELECT
  ${RESOURCE_SELECT}
FROM ed2k_resources r
${SOURCE_META_JOIN}
WHERE (${keywordFilter.replace(/filename/g, "r.filename").replace(/search_string/g, "r.search_string")})
${PUBLIC_RESOURCE_FILTER}
${timeFilter.replace(/created_at/g, "r.created_at").replace(/size/g, "r.size")}
${sizeFilter.replace(/size/g, "r.size")}
ORDER BY ${orderBy.replace(/filename/g, "r.filename").replace(/search_string/g, "r.search_string").replace(/size/g, "r.size").replace(/created_at/g, "r.created_at")}
LIMIT $${limitParamIndex}
OFFSET $${offsetParamIndex}
`;

    const params = [
      ...keywordsParams,
      ...scoringExtraParams,
      queryInput.limit,
      queryInput.offset,
    ];

    const queryArr = [query(sql, params)];

    if (queryInput.withTotalCount) {
      const countSql = `
SELECT COUNT(*) AS total
FROM ed2k_resources r
WHERE (${keywordFilter.replace(/filename/g, "r.filename").replace(/search_string/g, "r.search_string")})
${PUBLIC_RESOURCE_FILTER}
${timeFilter.replace(/created_at/g, "r.created_at").replace(/size/g, "r.size")}
${sizeFilter.replace(/size/g, "r.size")}
`;
      queryArr.push(query(countSql, [...keywordsParams]));
    } else {
      queryArr.push(Promise.resolve({ rows: [{ total: 0 }] }) as any);
    }

    const [{ rows: resourcesResp }, { rows: countResp }] =
      await Promise.all(queryArr);

    const resources = resourcesResp.map(formatResource);
    const total_count = Number(countResp[0]?.total || 0);
    const has_more =
      queryInput.withTotalCount &&
      queryInput.offset + queryInput.limit < total_count;

    return { keywords: keywordsPlain, resources, total_count, has_more };
  } catch (error) {
    console.error("Error in search resolver:", error);
    throw new Error("Failed to execute search query");
  }
}

export async function resourceByHash(_: unknown, { hash }: { hash: string }) {
  try {
    const sql = `
SELECT
  ${RESOURCE_SELECT}
FROM ed2k_resources r
${SOURCE_META_JOIN}
WHERE r.hash = $1
${PUBLIC_RESOURCE_FILTER}
LIMIT 1
`;

    const { rows } = await query(sql, [hash.toUpperCase()]);
    const resource = rows[0];

    if (!resource) {
      return null;
    }

    return formatResource(resource);
  } catch (error) {
    console.error("Error in resourceByHash resolver:", error);
    throw new Error("Failed to fetch resource by hash");
  }
}

export async function statsInfo() {
  try {
    const dbName = process.env.POSTGRES_DB || "ed2k";
    const sql = `
WITH db_size AS (
  SELECT pg_database_size('${dbName}') AS size
),
resource_count AS (
  SELECT COUNT(*) AS total_count FROM ed2k_resources r
  WHERE (
      lower(COALESCE(r.ed2k_link, '')) LIKE 'ed2k://%'
      OR lower(COALESCE(r.ed2k_link, '')) LIKE 'magnet:%'
      OR lower(COALESCE(r.ed2k_link, '')) LIKE '%115cdn.com/s/%'
      OR lower(COALESCE(r.ed2k_link, '')) LIKE '%115.com/s/%'
      OR lower(COALESCE(r.ed2k_link, '')) LIKE 'unavailable://%'
    )
),
latest_resource AS (
  SELECT *
  FROM ed2k_resources r
  WHERE (
      lower(COALESCE(r.ed2k_link, '')) LIKE 'ed2k://%'
      OR lower(COALESCE(r.ed2k_link, '')) LIKE 'magnet:%'
      OR lower(COALESCE(r.ed2k_link, '')) LIKE '%115cdn.com/s/%'
      OR lower(COALESCE(r.ed2k_link, '')) LIKE '%115.com/s/%'
      OR lower(COALESCE(r.ed2k_link, '')) LIKE 'unavailable://%'
    )
  ORDER BY created_at DESC
  LIMIT 1
)
SELECT
  db_size.size,
  latest_resource.created_at AS updated_at,
  resource_count.total_count,
  latest_resource.hash AS latest_resource_hash,
  json_build_object(
    'hash', latest_resource.hash,
    'name', latest_resource.filename,
    'size', latest_resource.size,
    'created_at', latest_resource.created_at,
    'updated_at', latest_resource.updated_at
  ) AS latest_resource
FROM db_size, resource_count, latest_resource
`;

    const { rows } = await query(sql, []);
    const data = rows[0];

    if (!data) {
      return null;
    }

    return {
      ...data,
      updated_at: toEpochSeconds(data.updated_at),
      latest_resource: {
        ...data.latest_resource,
        created_at: toEpochSeconds(data.latest_resource.created_at),
        updated_at: toEpochSeconds(data.latest_resource.updated_at),
      },
    };
  } catch (error) {
    console.error("Error in statsInfo resolver:", error);
    throw new Error("Failed to fetch resource stats");
  }
}

export async function latestResources(_: unknown, { limit = 20 }: { limit?: number }) {
  try {
    const safeLimit = Math.min(Math.max(Number(limit) || 20, 1), 50);
    const sql = `
SELECT
  ${RESOURCE_SELECT}
FROM ed2k_resources r
${SOURCE_META_JOIN}
WHERE TRUE
${PUBLIC_RESOURCE_FILTER}
ORDER BY r.created_at DESC
LIMIT $1
`;

    const { rows } = await query(sql, [safeLimit]);

    return rows.map(formatResource);
  } catch (error) {
    console.error("Error in latestResources resolver:", error);
    throw new Error("Failed to fetch latest resources");
  }
}

export async function randomResources(_: unknown, { limit = 20 }: { limit?: number }) {
  try {
    const safeLimit = Math.min(Math.max(Number(limit) || 20, 1), 50);
    const sql = `
SELECT
  ${LIST_RESOURCE_SELECT}
FROM ed2k_resources r
${LIST_META_JOIN}
WHERE TRUE
${PUBLIC_RESOURCE_FILTER}
ORDER BY RANDOM()
LIMIT $1
`;

    const { rows } = await query(sql, [safeLimit]);

    return rows.map(formatResource);
  } catch (error) {
    console.error("Error in randomResources resolver:", error);
    throw new Error("Failed to fetch random resources");
  }
}

/** 随便看看：按收录时间分页 */
export async function browseResources(
  _: unknown,
  {
    limit = 15,
    offset = 0,
    board_fid,
    board,
    board_parent,
  }: {
    limit?: number;
    offset?: number;
    board_fid?: string | null;
    board?: string | null;
    board_parent?: string | null;
  } = {},
): Promise<{ resources: ReturnType<typeof formatResource>[]; total_count: number }> {
  try {
    const safeLimit = Math.min(Math.max(Number(limit) || 15, 1), 50);
    const safeOffset = Math.max(Number(offset) || 0, 0);
    const fid = (board_fid || "").trim();
    const boardName = (board || "").trim();
    const parent = (board_parent || "").trim();

    const where: string[] = ["TRUE", PUBLIC_RESOURCE_FILTER.trim()];
    const params: unknown[] = [];
    let p = 1;

    if (fid) {
      // 子版 key（2:684）或旧纯 fid；名称兼容「·」与「-」
      const names = new Set<string>();
      if (boardName) {
        names.add(boardName);
        names.add(boardName.replace(/ · /g, "-"));
        names.add(boardName.replace(/-/g, " · "));
      }
      const nameList = Array.from(names).filter(Boolean);
      if (nameList.length) {
        where.push(
          `AND (rs.board_fid = $${p} OR replace(COALESCE(rs.board_name, ''), '-', ' · ') = ANY($${p + 1}::text[]))`,
        );
        params.push(fid, nameList.map((n) => n.replace(/-/g, " · ")));
        p += 2;
      } else {
        where.push(`AND rs.board_fid = $${p}`);
        params.push(fid);
        p += 1;
      }
    } else if (parent) {
      where.push(
        `AND (rs.board_name = $${p} OR rs.board_name LIKE $${p + 1} OR rs.board_name LIKE $${p + 2})`,
      );
      params.push(parent, `${parent} · %`, `${parent}-%`);
      p += 3;
    } else if (boardName) {
      where.push(
        `AND replace(COALESCE(rs.board_name, ''), '-', ' · ') = $${p}`,
      );
      params.push(boardName.replace(/-/g, " · "));
      p += 1;
    }

    const whereSql = where.join("\n");
    const listSql = `
SELECT
  ${LIST_RESOURCE_SELECT}
FROM ed2k_resources r
${LIST_META_JOIN}
WHERE ${whereSql}
ORDER BY r.created_at DESC
LIMIT $${p} OFFSET $${p + 1}
`;
    const countSql = `
SELECT COUNT(*)::int AS total_count
FROM ed2k_resources r
${LIST_META_JOIN}
WHERE ${whereSql}
`;

    const [listRes, countRes] = await Promise.all([
      query(listSql, [...params, safeLimit, safeOffset]),
      query(countSql, params),
    ]);

    return {
      resources: listRes.rows.map(formatResource),
      total_count: Number(countRes.rows[0]?.total_count || 0),
    };
  } catch (error) {
    console.error("Error in browseResources:", error);
    throw new Error(
      `Failed to fetch browse resources: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}
