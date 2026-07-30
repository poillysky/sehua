import {
  fetchText,
  uniqNames,
  type PartialMeta,
} from "./http.js";
import {
  absUrl,
  cleanTitle,
  collectByRe,
  pickOgImage,
  pickOgTitle,
  splitTitleLang,
} from "./util.js";

/** AVSOX / AVMOO 结构相近 */
export async function scrapeAvsoxFamily(
  code: string,
  opts: { baseUrl: string; source: string; langPath?: string },
): Promise<PartialMeta> {
  const base = opts.baseUrl.replace(/\/$/, "");
  const lang = opts.langPath || "cn";
  const searchUrl = `${base}/${lang}/search/${encodeURIComponent(code)}`;
  const search = await fetchText(searchUrl, { referer: `${base}/` });

  const moviePath =
    search.match(
      new RegExp(
        `href=["']([^"']*/${lang}/movie/[^"']+)["'][^>]*>[\\s\\S]{0,120}?${code.replace(/-/g, "[-]?")}`,
        "i",
      ),
    )?.[1] ||
    search.match(
      new RegExp(`href=["']([^"']*/${lang}/movie/[^"']+)["']`, "i"),
    )?.[1];
  if (!moviePath) throw new Error(`${opts.source} no result`);

  const detailUrl = absUrl(moviePath, base);
  const html = await fetchText(detailUrl, { referer: searchUrl });
  const title = cleanTitle(pickOgTitle(html) || html.match(/<h3[^>]*>([\s\S]*?)<\/h3>/i)?.[1], code);
  const langs = splitTitleLang(title);

  const actresses = uniqNames(
    collectByRe(html, /href=["'][^"']*\/star\/[^"']+["'][^>]*>([^<]+)</gi),
  );

  let cover =
    html.match(/class=["']bigImage["'][^>]*href=["']([^"']+)["']/i)?.[1] ||
    pickOgImage(html);
  if (cover) cover = absUrl(cover, detailUrl);

  return {
    ...langs,
    actresses,
    cover_url: cover,
    source: opts.source,
  };
}

export async function scrapeAvsox(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  return scrapeAvsoxFamily(code, {
    baseUrl: opts?.baseUrl || "https://avsox.click",
    source: "avsox",
  });
}

export async function scrapeAvmoo(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  return scrapeAvsoxFamily(code, {
    baseUrl: opts?.baseUrl || "https://avmoo.online",
    source: "avmoo",
  });
}
