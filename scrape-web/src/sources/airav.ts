import {
  fetchText,
  stripTags,
  uniqNames,
  type PartialMeta,
} from "./http.js";

export type AiravOpts = {
  wikiBase?: string;
  ioBase?: string;
  useWiki?: boolean;
  useIo?: boolean;
};

/**
 * Airav：偏中文片名 / 女优。
 * wiki / io 可按配置分别启用。
 */
export async function scrapeAirav(
  code: string,
  opts: AiravOpts = {},
): Promise<PartialMeta> {
  const useWiki = opts.useWiki !== false;
  const useIo = opts.useIo !== false;
  const wikiBase = (opts.wikiBase || "https://www.airav.wiki").replace(
    /\/$/,
    "",
  );
  const ioBase = (opts.ioBase || "https://airav.io/cn")
    .replace(/\/$/, "")
    .replace(/\/cn$/i, "");
  // 搜索走 /cn 语言站
  const ioCn = `${ioBase}/cn`;

  const errors: string[] = [];
  if (useWiki) {
    try {
      return await scrapeAiravWiki(code, wikiBase);
    } catch (err) {
      errors.push(err instanceof Error ? err.message : String(err));
    }
  }
  if (useIo) {
    try {
      return await scrapeAiravIo(code, ioCn);
    } catch (err) {
      errors.push(err instanceof Error ? err.message : String(err));
    }
  }
  if (!useWiki && !useIo) throw new Error("airav disabled");
  throw new Error(`airav failed: ${errors.join("; ")}`);
}

async function scrapeAiravWiki(
  code: string,
  base: string,
): Promise<PartialMeta> {
  const url = `${base}/video/${encodeURIComponent(code)}`;
  const html = await fetchText(url, { referer: `${base}/` });
  if (/找不到|404|Not Found/i.test(html) && !/video-title|actress/i.test(html)) {
    throw new Error("airav.wiki not found");
  }

  const title =
    pick(
      html,
      /property=["']og:title["']\s+content=["']([^"']+)["']/i,
      /<h1[^>]*>([\s\S]*?)<\/h1>/i,
    ) || null;
  const cleaned = title
    ? stripTags(title)
        .replace(new RegExp(`^${code}\\s*`, "i"), "")
        .replace(/\s*[-–—]\s*airav(?:\.io|\.wiki)?\s*$/i, "")
        .trim()
    : null;

  const actresses: string[] = [];
  const re =
    /href=["'][^"']*\/actress\/[^"']+["'][^>]*>([^<]+)</gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) {
    actresses.push(stripTags(m[1]));
  }

  const cover =
    pick(
      html,
      /property=["']og:image["']\s+content=["']([^"']+)["']/i,
      /content=["']([^"']+)["']\s+property=["']og:image["']/i,
    ) || null;

  const zh = cleaned && isLikelyChinese(cleaned) ? cleaned : null;
  return {
    title_zh: zh,
    title_ja: cleaned && !zh ? cleaned : null,
    actresses: uniqNames(actresses),
    cover_url: cover,
    source: "airav",
  };
}

async function scrapeAiravIo(code: string, base: string): Promise<PartialMeta> {
  const searchUrl = `${base}/search_result?kw=${encodeURIComponent(code)}`;
  const html = await fetchText(searchUrl, { referer: `${base}/` });
  const detailHref =
    html.match(
      new RegExp(`href=["']([^"']*\\/video\\/${code}[^"']*)["']`, "i"),
    )?.[1] ||
    html.match(/href=["']([^"']*\/video\/[^"']+)["']/i)?.[1];
  if (!detailHref) throw new Error("airav.io no result");
  const detailUrl = new URL(detailHref, base).toString();
  const detail = await fetchText(detailUrl, { referer: searchUrl });

  const title =
    pick(
      detail,
      /property=["']og:title["']\s+content=["']([^"']+)["']/i,
      /<h1[^>]*>([\s\S]*?)<\/h1>/i,
    ) || null;
  const cleaned = title
    ? stripTags(title)
        .replace(new RegExp(`^${code}\\s*`, "i"), "")
        .replace(/\s*[-–—]\s*airav(?:\.io|\.wiki)?\s*$/i, "")
        .trim()
    : null;

  const actresses: string[] = [];
  const re = /href=["'][^"']*actress[^"']*["'][^>]*>([^<]+)</gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(detail)) !== null) {
    actresses.push(stripTags(m[1]));
  }

  const cover =
    pick(
      detail,
      /property=["']og:image["']\s+content=["']([^"']+)["']/i,
    ) || null;

  const zh = cleaned && isLikelyChinese(cleaned) ? cleaned : null;
  return {
    title_zh: zh,
    title_ja: cleaned && !zh ? cleaned : null,
    actresses: uniqNames(actresses),
    cover_url: cover,
    source: "airav_io",
  };
}

function isLikelyChinese(title: string): boolean {
  if (!/[\u4e00-\u9fff]/.test(title)) return false;
  if (/[\u3040-\u30ff]/.test(title)) return false;
  return true;
}

function pick(html: string, ...patterns: RegExp[]): string | null {
  for (const re of patterns) {
    const m = html.match(re);
    if (m?.[1]) return m[1];
  }
  return null;
}
