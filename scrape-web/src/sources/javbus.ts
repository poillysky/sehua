import {
  fetchText,
  stripTags,
  uniqNames,
  type PartialMeta,
} from "./http.js";

/** JavBus：封面 + 标题 + 女优 */
export async function scrapeJavbus(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const base = (opts?.baseUrl || "https://www.javbus.com").replace(/\/$/, "");
  const url = `${base}/${encodeURIComponent(code)}`;
  const html = await fetchText(url, { referer: `${base}/` });

  if (
    /404|找不到頁面|找不到页面|Page Not Found/i.test(html) &&
    !/bigImage|movie-title|container/i.test(html)
  ) {
    throw new Error("javbus not found");
  }

  const titleMatch =
    html.match(/<h3[^>]*>([\s\S]*?)<\/h3>/i) ||
    html.match(/property=["']og:title["']\s+content=["']([^"']+)["']/i) ||
    html.match(/content=["']([^"']+)["']\s+property=["']og:title["']/i);
  let title = titleMatch?.[1] ? stripTags(titleMatch[1]) : null;
  if (title) {
    title = title.replace(new RegExp(`^${code}\\s*`, "i"), "").trim() || title;
  }

  const actresses: string[] = [];
  const starRe =
    /<div[^>]*class=["'][^"']*star-name[^"']*["'][^>]*>[\s\S]*?<a[^>]*>([^<]+)<\/a>/gi;
  let m: RegExpExecArray | null;
  while ((m = starRe.exec(html)) !== null) {
    actresses.push(stripTags(m[1]));
  }
  if (!actresses.length) {
    const altRe = /\/star\/[^"']+["'][^>]*>([^<]+)</gi;
    while ((m = altRe.exec(html)) !== null) {
      actresses.push(stripTags(m[1]));
    }
  }

  let cover_url: string | null = null;
  const big =
    html.match(/class=["']bigImage["'][^>]*href=["']([^"']+)["']/i) ||
    html.match(/href=["']([^"']+)["'][^>]*class=["']bigImage["']/i) ||
    html.match(
      /<a[^>]*class=["'][^"']*bigImage[^"']*["'][^>]*href=["']([^"']+)["']/i,
    );
  if (big?.[1]) {
    cover_url = new URL(big[1], url).toString();
  } else {
    const og = html.match(
      /property=["']og:image["']\s+content=["']([^"']+)["']/i,
    );
    if (og?.[1]) cover_url = og[1];
  }

  const hasKana = title ? /[\u3040-\u30ff]/.test(title) : false;
  const hasHan = title ? /[\u4e00-\u9fff]/.test(title) : false;
  const isZh = Boolean(title && hasHan && !hasKana);

  return {
    title_zh: isZh ? title : null,
    title_ja: title && !isZh ? title : null,
    actresses: uniqNames(actresses),
    cover_url,
    source: "javbus",
  };
}
