import { Ed2kResourceProps } from "@/types";

/** 无有效子资源名：空、纯 hash、磁力占位 magnet-xxxxxxxx */
const PLACEHOLDER_MAGNET_NAME_RE = /^magnet-[0-9a-f]{8}$/i;

function isMissingSubName(
  name?: string | null,
  hash?: string | null,
): boolean {
  const n = (name || "").trim();
  if (!n) return true;
  const h = (hash || "").trim().toUpperCase();
  if (h && n.toUpperCase() === h) return true;
  if (h.length >= 8 && n.toUpperCase() === h.slice(0, 8)) return true;
  if (PLACEHOLDER_MAGNET_NAME_RE.test(n)) return true;
  return false;
}

/** ed2k URI / magnet dn= 链内技术名（不是子资源名） */
function linkEmbeddedName(
  item: Pick<Ed2kResourceProps, "ed2k_link" | "ed2k_links">,
): string | null {
  const links = [
    ...(Array.isArray(item.ed2k_links) ? item.ed2k_links : []),
    item.ed2k_link || "",
  ].filter(Boolean);

  for (const link of links) {
    const ed2k = parseEd2kLink(link);
    if (ed2k?.filename) {
      try {
        return decodeURIComponent(ed2k.filename).trim();
      } catch {
        return ed2k.filename.trim();
      }
    }
    const dn = link.match(/[?&]dn=([^&]+)/i);
    if (dn?.[1]) {
      try {
        return decodeURIComponent(dn[1].replace(/\+/g, " ")).trim();
      } catch {
        return dn[1].trim();
      }
    }
  }
  return null;
}

export function getDisplayTitle(
  item: Pick<
    Ed2kResourceProps,
    "title" | "name" | "description" | "hash" | "ed2k_link" | "ed2k_links"
  >,
) {
  // 子资源名 = 帖内【资源名称】/【影片名称】，不是 ed2k/dn 链内名
  // 多资源时 name 已是各条目上下文标题
  const fromDesc =
    getDescriptionField(item.description, "资源名称") ||
    getDescriptionField(item.description, "影片名称");
  const name = item.name?.trim() || "";
  const title = item.title?.trim() || "";
  const embedded = linkEmbeddedName(item);
  const nameOk =
    !isMissingSubName(name, item.hash) &&
    (!embedded || name.toLowerCase() !== embedded.toLowerCase());

  if (nameOk && name !== title) {
    return name;
  }
  if (fromDesc) {
    return fromDesc;
  }
  if (nameOk) {
    return name;
  }
  return title || name || "";
}

export function getDisplayFilename(
  item: Pick<
    Ed2kResourceProps,
    "title" | "name" | "description" | "hash" | "ed2k_link" | "ed2k_links"
  >,
) {
  // 子资源与主资源不同时，返回主资源名作次要信息
  const name = getDisplayTitle(item);
  const title = item.title?.trim();

  if (!title || !name || title === name) {
    return null;
  }

  return title;
}

export type DescriptionLine = {
  label: string;
  value: string;
};

const DISPLAY_DESCRIPTION_LABELS = [
  "资源名称",
  "资源类型",
  "资源大小",
  "是否有码",
  "有无水印",
  "资源数量",
  "解压密码",
  "影片名称",
  "出演女优",
] as const;

const DESCRIPTION_LABEL_ALIASES: Record<string, (typeof DISPLAY_DESCRIPTION_LABELS)[number]> = {
  有无第三方水印: "有无水印",
  影片容量: "资源大小",
  影片大小: "资源大小",
  文件大小: "资源大小",
  提取密码: "解压密码",
  资源密码: "解压密码",
  资源解压密码: "解压密码",
  影片名稱: "影片名称",
  資源名稱: "资源名称",
};

export function formatDescriptionLines(description?: string | null): DescriptionLine[] {
  const text = description?.trim();

  if (!text) {
    return [];
  }

  const picked = new Map<string, string>();

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    const match = line.match(/^【([^】]+)】(.*)$/);

    if (!match) {
      continue;
    }

    const rawLabel = match[1].trim();
    const canonical =
      DESCRIPTION_LABEL_ALIASES[rawLabel] ||
      (DISPLAY_DESCRIPTION_LABELS.includes(rawLabel as (typeof DISPLAY_DESCRIPTION_LABELS)[number])
        ? (rawLabel as (typeof DISPLAY_DESCRIPTION_LABELS)[number])
        : null);

    if (!canonical || picked.has(canonical)) {
      continue;
    }

    const value = match[2].trim().replace(/^[:：]+/, "");
    if (!value) {
      continue;
    }

    picked.set(canonical, value);
  }

  return DISPLAY_DESCRIPTION_LABELS.filter((label) => picked.has(label)).map((label) => ({
    label,
    value: picked.get(label)!,
  }));
}

export function getDescriptionField(
  description: string | null | undefined,
  label: string,
): string | null {
  const lines = formatDescriptionLines(description);

  return lines.find((line) => line.label === label)?.value || null;
}

/** 优先库字段，其次描述里的【解压密码】行 */
export function getExtractPassword(
  item: Pick<Ed2kResourceProps, "extract_password" | "description">,
): string | null {
  const fromCol = item.extract_password?.trim();

  if (fromCol) {
    return fromCol;
  }

  return (
    getDescriptionField(item.description, "解压密码") ||
    getDescriptionField(item.description, "访问码") ||
    getDescriptionField(item.description, "分享码")
  );
}

const MAX_PREVIEW_IMAGES = 5;

const IMAGE_EXT_RE = /\.(jpe?g|png|gif|webp|bmp)(\?|#|$)/i;

const INVALID_IMAGE_MARKERS = [
  "filetype",
  "hrline",
  "smiley",
  "/static/image/common/",
  "static/image/",
  "avatar",
  "attachment/common/",
  "usergroup_icon",
  "groupicon",
  "favicon",
];

export function filterPreviewImages(images?: string[] | null): string[] {
  return (images || [])
    .filter(Boolean)
    .filter((src) => {
      const lower = src.toLowerCase();

      if (INVALID_IMAGE_MARKERS.some((marker) => lower.includes(marker))) {
        return false;
      }

      if (lower.includes(".txt")) {
        return false;
      }

      return IMAGE_EXT_RE.test(lower) || lower.includes("/tupian/forum/");
    })
    .slice(0, MAX_PREVIEW_IMAGES);
}

export { MAX_PREVIEW_IMAGES };

const ED2K_LINK_RE =
  /ed2k:\/\/\|file\|([^|]+)\|(\d+)\|([A-Fa-f0-9]{32})\|/i;
const MAGNET_HASH_RE =
  /magnet:\?xt=urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})/i;

export function isPublicDownloadLink(link?: string | null): boolean {
  const lower = (link || "").trim().toLowerCase();

  if (!lower || lower.startsWith("unavailable://")) {
    return false;
  }

  if (lower.startsWith("ed2k://") || lower.startsWith("magnet:")) {
    return true;
  }

  return (
    lower.includes("115cdn.com/s/") || lower.includes("115.com/s/")
  );
}

export function linkKindOf(
  link?: string | null,
): "ed2k" | "magnet" | "stub" | "115share" | "other" {
  const lower = (link || "").trim().toLowerCase();

  if (lower.startsWith("magnet:")) {
    return "magnet";
  }

  if (lower.startsWith("ed2k://")) {
    return "ed2k";
  }

  if (lower.startsWith("unavailable://")) {
    return "stub";
  }

  if (lower.includes("115cdn.com/s/") || lower.includes("115.com/s/")) {
    return "115share";
  }

  return "other";
}

/** ED2K MD4：32 位十六进制；磁力 infohash：40 位十六进制。 */
export const RESOURCE_HASH_REGEX = /^[a-f0-9]{32}([a-f0-9]{8})?$/i;

export function isResourceHash(hash?: string | null): boolean {
  return !!hash && RESOURCE_HASH_REGEX.test(hash);
}

export function parseEd2kLink(link: string) {
  const match = link.match(ED2K_LINK_RE);

  if (!match) {
    return null;
  }

  return {
    filename: match[1],
    size: match[2],
    hash: match[3].toUpperCase(),
    link,
  };
}

export function parseMagnetLink(link: string) {
  const match = link.match(MAGNET_HASH_RE);

  if (!match) {
    return null;
  }

  return {
    hash: match[1].toUpperCase(),
    link,
  };
}

export function normalizeEd2kLinks(
  ed2kLinks?: string[] | null,
  fallbackLink?: string | null,
): string[] {
  const raw = (Array.isArray(ed2kLinks) && ed2kLinks.length
    ? ed2kLinks
    : fallbackLink
      ? [fallbackLink]
      : []
  ).filter(Boolean);

  return Array.from(new Set(raw.filter((link) => isPublicDownloadLink(link))));
}

/** 链接是否属于该资源 hash（磁力 infohash / ed2k MD4）。解析不出 hash 的链（如 115）视为可保留。 */
export function linkMatchesResourceHash(
  link: string | null | undefined,
  hash: string | null | undefined,
): boolean {
  const h = (hash || "").trim().toUpperCase();
  if (!h) return true;
  const raw = (link || "").trim();
  if (!raw) return false;

  const ed2k = parseEd2kLink(raw);
  if (ed2k?.hash) {
    return ed2k.hash.toUpperCase() === h;
  }
  const magnet = parseMagnetLink(raw);
  if (magnet?.hash) {
    return magnet.hash.toUpperCase() === h;
  }
  return true;
}

/**
 * 一 hash 一条资源：只保留属于本 hash 的链接。
 * 合集帖旧数据可能把整帖多链写进 rs.ed2k_links，会盖住正确的 r.ed2k_link。
 */
export function linksForResourceHash(
  hash: string | null | undefined,
  ed2kLinks?: string[] | null,
  fallbackLink?: string | null,
): string[] {
  const h = (hash || "").trim().toUpperCase();
  const primary = (fallbackLink || "").trim();
  const fromMeta = normalizeEd2kLinks(ed2kLinks, null).filter((link) =>
    linkMatchesResourceHash(link, h),
  );

  const out: string[] = [];
  const push = (link: string) => {
    if (!link || out.includes(link)) return;
    if (!isPublicDownloadLink(link) && !link.toLowerCase().startsWith("unavailable://")) {
      return;
    }
    if (h && isPublicDownloadLink(link) && !linkMatchesResourceHash(link, h)) {
      return;
    }
    out.push(link);
  };

  // 以资源表主链为准
  if (primary) push(primary);
  for (const link of fromMeta) push(link);

  if (!out.length && primary) {
    return [primary];
  }
  return out;
}

export function getEd2kCopyText(
  item: Pick<Ed2kResourceProps, "hash" | "ed2k_link" | "ed2k_links">,
): string {
  return linksForResourceHash(item.hash, item.ed2k_links, item.ed2k_link).join("\n");
}

export function getEd2kLinkCount(
  item: Pick<Ed2kResourceProps, "hash" | "ed2k_link" | "ed2k_links">,
): number {
  return linksForResourceHash(item.hash, item.ed2k_links, item.ed2k_link).length;
}

export type Ed2kResourceItem = {
  index: number;
  filename: string;
  size: string;
  hash: string;
  link: string;
  extension: string;
};

export function getEd2kResourceList(
  item: Pick<Ed2kResourceProps, "name" | "hash" | "size" | "ed2k_link" | "ed2k_links">,
): Ed2kResourceItem[] {
  const links = linksForResourceHash(item.hash, item.ed2k_links, item.ed2k_link);

  return links.map((link, index) => {
    const parsed = parseEd2kLink(link);
    const magnet = parseMagnetLink(link);
    const filename = parsed?.filename || item.name;

    return {
      index: index + 1,
      filename,
      size: parsed?.size || String(item.size),
      hash: parsed?.hash || magnet?.hash || item.hash,
      link,
      extension: filename.includes(".") ? filename.split(".").pop() || "" : "",
    };
  });
}

export function getEd2kTotalSize(
  item: Pick<Ed2kResourceProps, "name" | "hash" | "size" | "ed2k_link" | "ed2k_links">,
): number {
  return getEd2kResourceList(item).reduce(
    (sum, resource) => sum + Number(resource.size || 0),
    0,
  );
}

export function getEd2kDisplaySize(
  item: Pick<Ed2kResourceProps, "name" | "hash" | "size" | "ed2k_link" | "ed2k_links">,
): number {
  const linkCount = getEd2kLinkCount(item);

  if (linkCount <= 1) {
    return Number(item.size || 0);
  }

  const totalSize = getEd2kTotalSize(item);

  return totalSize || Number(item.size || 0);
}

const ARCHIVE_EXT_RE = /\.(zip|rar|7z)(?:\.[a-z0-9]+)?$/i;

/** 文件名是否为可云解压压缩包（zip / rar / 7z） */
export function isArchiveFilename(name?: string | null): boolean {
  const raw = decodeURIComponent((name || "").trim());

  return ARCHIVE_EXT_RE.test(raw);
}

/** 链接或资源是否指向压缩包（供转存后一键云解压） */
export function isArchiveDownloadLink(link?: string | null): boolean {
  const parsed = parseEd2kLink(link || "");

  if (parsed?.filename) {
    return isArchiveFilename(parsed.filename);
  }
  const lower = (link || "").trim().toLowerCase();

  return ARCHIVE_EXT_RE.test(lower);
}

export function hasArchiveEd2k(
  item: Pick<Ed2kResourceProps, "name" | "hash" | "ed2k_link" | "ed2k_links">,
): boolean {
  if (isArchiveFilename(item.name)) {
    return true;
  }

  return linksForResourceHash(item.hash, item.ed2k_links, item.ed2k_link).some((link) =>
    isArchiveDownloadLink(link),
  );
}
