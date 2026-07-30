import {
  fetchText,
  uniqNames,
  type PartialMeta,
} from "./http.js";
import { undiciFetch } from "./http.js";
import {
  absUrl,
  cleanTitle,
  collectByRe,
  pickOgImage,
  pickOgTitle,
  splitTitleLang,
} from "./util.js";

/** JAV321：POST 搜索 */
export async function scrapeJav321(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const base = (opts?.baseUrl || "https://www.jav321.com").replace(/\/$/, "");
  const res = await undiciFetch(`${base}/search`, {
    method: "POST",
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
      "Content-Type": "application/x-www-form-urlencoded",
      Referer: `${base}/`,
      Accept: "text/html",
    },
    body: `sn=${encodeURIComponent(code)}`,
    redirect: "follow",
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) throw new Error(`jav321 HTTP ${res.status}`);
  const html = await res.text();
  if (/還沒有人投稿|not found|找不到/i.test(html) && !/og:title/i.test(html)) {
    throw new Error("jav321 not found");
  }

  const title = cleanTitle(pickOgTitle(html), code);
  const langs = splitTitleLang(title);
  const actresses = uniqNames(
    collectByRe(html, /href=["'][^"']*\/star\/[^"']+["'][^>]*>([^<]+)</gi),
  );
  let cover = pickOgImage(html);
  if (cover) cover = absUrl(cover, base);

  return {
    ...langs,
    actresses,
    cover_url: cover,
    source: "jav321",
  };
}

/** JavLibrary */
export async function scrapeJavlibrary(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  // base 可为 https://www.javlibrary.com 或 .../cn
  const root = (opts?.baseUrl || "https://www.javlibrary.com")
    .replace(/\/$/, "")
    .replace(/\/cn$/i, "");
  const cn = `${root}/cn`;
  const searchUrl = `${cn}/vl_searchbyid.php?keyword=${encodeURIComponent(code)}`;
  const search = await fetchText(searchUrl, { referer: `${cn}/` });

  // 可能直接进详情，也可能是列表
  let html = search;
  let detailUrl = searchUrl;
  if (/id=["']video_title["']/i.test(search) === false) {
    const path =
      search.match(
        new RegExp(
          `href=["']\\.\\.?(/\\?v=[^"']+)["'][^>]*>[\\s\\S]{0,80}?${code.replace(/-/g, "[-]?")}`,
          "i",
        ),
      )?.[1] ||
      search.match(/href=["']\.?\.?(\/\?v=[^"']+)["']/i)?.[1];
    if (!path) throw new Error("javlibrary no result");
    detailUrl = absUrl(path.replace(/^\.\./, ""), `${cn}/`);
    html = await fetchText(detailUrl, { referer: searchUrl });
  }

  const title = cleanTitle(
    html.match(/id=["']video_title["'][^>]*>[\s\S]*?<a[^>]*>([\s\S]*?)<\/a>/i)?.[1] ||
      pickOgTitle(html),
    code,
  );
  const langs = splitTitleLang(title);
  const actresses = uniqNames(
    collectByRe(
      html,
      /href=["'][^"']*star\.php\?[^"']*["'][^>]*rel=["']tag["'][^>]*>([^<]+)</gi,
    ),
  );
  let cover =
    html.match(/id=["']video_jacket_img["'][^>]*src=["']([^"']+)["']/i)?.[1] ||
    pickOgImage(html);
  if (cover) cover = absUrl(cover, detailUrl);

  return {
    ...langs,
    actresses,
    cover_url: cover,
    source: "javlibrary",
  };
}
