import {
  fetchText,
  uniqNames,
  type PartialMeta,
} from "./http.js";
import {
  absUrl,
  cleanTitle,
  collectByRe,
  pageMentionsCode,
  pickOgImage,
  pickOgTitle,
  splitTitleLang,
} from "./util.js";

/** JavDB：搜索 → 详情；校验番号防串片 */
export async function scrapeJavdb(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const base = (opts?.baseUrl || "https://javdb.com").replace(/\/$/, "");
  const searchUrl = `${base}/search?q=${encodeURIComponent(code)}&f=all`;
  const search = await fetchText(searchUrl, { referer: `${base}/` });

  const detailPath =
    search.match(
      new RegExp(
        `href=["'](/v/[^"']+)["'][^>]*>[\\s\\S]{0,200}?${code.replace(/-/g, "[-]?")}`,
        "i",
      ),
    )?.[1] ||
    search.match(/href=["'](\/v\/[^"']+)["']/i)?.[1];
  if (!detailPath) throw new Error("javdb no result");

  const detailUrl = absUrl(detailPath, base);
  const html = await fetchText(detailUrl, { referer: searchUrl });
  if (!pageMentionsCode(html, code)) throw new Error("javdb code mismatch");

  const title = cleanTitle(pickOgTitle(html), code);
  const langs = splitTitleLang(title);

  // 只收 ♀ 演員；♂（导演等）会挂在同一 /actors/ 链接下
  const actresses = uniqNames(
    collectByRe(
      html,
      /href=["'][^"']*\/actors\/[^"']+["'][^>]*>([^<]+)<\/a>\s*<strong[^>]*class=["'][^"']*female[^"']*["'][^>]*>/gi,
    ).filter((n) => n.length >= 2 && n.length <= 20),
  );

  let cover = pickOgImage(html);
  const coverBig = html.match(
    /class=["'][^"']*video-cover[^"']*["'][^>]*src=["']([^"']+)["']/i,
  )?.[1];
  if (coverBig) cover = absUrl(coverBig, detailUrl);
  if (cover) cover = absUrl(cover, detailUrl);

  return {
    title_zh: langs.title_zh,
    title_ja: langs.title_ja,
    actresses,
    cover_url: cover,
    source: "javdb",
  };
}
