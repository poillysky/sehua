import { Ed2kResourceProps } from "@/types";

export function getDisplayTitle(item: Pick<Ed2kResourceProps, "title" | "name">) {
  const title = item.title?.trim();

  return title || item.name;
}

export function getDisplayFilename(item: Pick<Ed2kResourceProps, "title" | "name">) {
  const title = item.title?.trim();

  if (!title || title === item.name) {
    return null;
  }

  return item.name;
}

export type DescriptionLine = {
  label: string;
  value: string;
};

const DISPLAY_DESCRIPTION_LABELS = [
  "资源名称",
  "资源类型",
  "有无水印",
  "资源数量",
  "解压密码",
  "影片名称",
  "出演女优",
  "是否有码",
] as const;

const DESCRIPTION_LABEL_ALIASES: Record<string, (typeof DISPLAY_DESCRIPTION_LABELS)[number]> = {
  有无第三方水印: "有无水印",
  是否有码: "是否有码",
  资源大小: "资源数量",
  影片容量: "资源数量",
  提取密码: "解压密码",
  资源解压密码: "解压密码",
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

  return getDescriptionField(item.description, "解压密码");
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

  return lower.startsWith("ed2k://") || lower.startsWith("magnet:");
}

export function linkKindOf(link?: string | null): "ed2k" | "magnet" | "other" {
  const lower = (link || "").trim().toLowerCase();

  if (lower.startsWith("magnet:")) {
    return "magnet";
  }

  if (lower.startsWith("ed2k://")) {
    return "ed2k";
  }

  return "other";
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

export function getEd2kCopyText(
  item: Pick<Ed2kResourceProps, "ed2k_link" | "ed2k_links">,
): string {
  return normalizeEd2kLinks(item.ed2k_links, item.ed2k_link).join("\n");
}

export function getEd2kLinkCount(
  item: Pick<Ed2kResourceProps, "ed2k_link" | "ed2k_links">,
): number {
  return normalizeEd2kLinks(item.ed2k_links, item.ed2k_link).length;
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
  const links = normalizeEd2kLinks(item.ed2k_links, item.ed2k_link);

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
