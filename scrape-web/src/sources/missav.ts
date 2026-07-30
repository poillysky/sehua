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

/** MissAV */
export async function scrapeMissav(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const base = (opts?.baseUrl || "https://missav123.com").replace(/\/$/, "");
  const slug = code.toLowerCase();
  const candidates = [
    `${base}/cn/${slug}`,
    `${base}/${slug}`,
    `${base}/cn/search/${encodeURIComponent(code)}`,
  ];

  let html = "";
  let detailUrl = candidates[0];
  let lastErr = "";
  for (const url of candidates) {
    try {
      const page = await fetchText(url, { referer: `${base}/` });
      if (/404|找不到|Not Found/i.test(page) && !/og:title/i.test(page)) {
        lastErr = "not found";
        continue;
      }
      if (/\/cn\/search\//i.test(url)) {
        const href = page.match(
          new RegExp(`href=["']([^"']*${slug}[^"']*)["']`, "i"),
        )?.[1];
        if (!href) {
          lastErr = "search empty";
          continue;
        }
        detailUrl = absUrl(href, base);
        html = await fetchText(detailUrl, { referer: url });
      } else {
        detailUrl = url;
        html = page;
      }
      if (!pageMentionsCode(html, code)) {
        lastErr = "code mismatch";
        html = "";
        continue;
      }
      break;
    } catch (err) {
      lastErr = err instanceof Error ? err.message : String(err);
    }
  }
  if (!html) throw new Error(lastErr || "missav failed");

  const title = cleanTitle(pickOgTitle(html), code);
  const langs = splitTitleLang(title);
  const actresses = uniqNames(
    collectByRe(
      html,
      /href=["'][^"']*\/actresses\/[^"']+["'][^>]*>([^<]+)</gi,
    ),
  );
  let cover = pickOgImage(html);
  if (cover) cover = absUrl(cover, detailUrl);

  return {
    ...langs,
    actresses,
    cover_url: cover,
    source: "miss_av",
  };
}

/** 7MMTV */
export async function scrape7mmtv(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  // base 可为 https://7mmtv.sx 或 .../zh
  const root = (opts?.baseUrl || "https://7mmtv.sx")
    .replace(/\/$/, "")
    .replace(/\/zh$/i, "");
  const searchUrl = `${root}/zh/searchform_search/all/index.html?search_keyword=${encodeURIComponent(code)}`;
  let search: string;
  try {
    search = await fetchText(searchUrl, { referer: `${root}/` });
  } catch {
    const alt = `${root}/zh/search/${encodeURIComponent(code)}.html`;
    search = await fetchText(alt, { referer: `${root}/` });
  }

  const codeRe = code.replace(/-/g, "[-]?");
  const href =
    search.match(
      new RegExp(`href=["']([^"']+)["'][^>]*>\\s*[^<]*${codeRe}[^<]*<`, "i"),
    )?.[1] ||
    search.match(new RegExp(`href=["']([^"']*${codeRe}[^"']*)["']`, "i"))?.[1];
  if (!href) throw new Error("7mmtv no result");
  const detailUrl = absUrl(href, root);
  const html = await fetchText(detailUrl, { referer: searchUrl });
  if (!pageMentionsCode(html, code)) throw new Error("7mmtv code mismatch");

  const title = cleanTitle(pickOgTitle(html), code);
  const langs = splitTitleLang(title);
  const actresses = uniqNames(
    collectByRe(
      html,
      /href=["'][^"']*\/zh\/[^"']*actress[^"']*["'][^>]*>([^<]+)</gi,
    ),
  );
  let cover = pickOgImage(html);
  if (cover) cover = absUrl(cover, detailUrl);

  return {
    ...langs,
    actresses,
    cover_url: cover,
    source: "sevenmmtv",
  };
}

/** FreeJavBT：封面可用；中文片名经常串片，调用方勿信任 title_zh */
export async function scrapeFreejavbt(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const base = (opts?.baseUrl || "https://freejavbt.com").replace(/\/$/, "");
  const url = `${base}/${encodeURIComponent(code)}/`;
  const html = await fetchText(url, { referer: `${base}/` });
  if (/404|找不到|Not Found/i.test(html) && !/og:title/i.test(html)) {
    throw new Error("freejavbt not found");
  }
  if (!pageMentionsCode(html, code)) throw new Error("freejavbt code mismatch");
  const title = cleanTitle(pickOgTitle(html), code);
  const actresses = uniqNames(
    collectByRe(html, /href=["'][^"']*\/actor\/[^"']+["'][^>]*>([^<]+)</gi),
  );
  // 片名含明显他人艺名且不在女优列表 → 丢弃片名，只留封面
  let langs = splitTitleLang(title);
  if (langs.title_zh) {
    const blob = actresses.join("");
    if (
      /三上悠[亞亚]|橋本有菜|桥本有菜|明日花[綺绮]羅|河北彩花/i.test(
        langs.title_zh,
      ) &&
      !/三上悠|橋本有菜|桥本有菜|明日花|河北彩花/.test(blob)
    ) {
      langs = { title_zh: null, title_ja: null };
    }
  }
  let cover = pickOgImage(html);
  if (cover) cover = absUrl(cover, url);
  return {
    ...langs,
    actresses,
    cover_url: cover,
    source: "freejavbt",
  };
}
