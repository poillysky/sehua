import {
  fetchText,
  stripTags,
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

/** MGStage：番号多为数字开头，如 259LUXU-001 */
export async function scrapeMgstage(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const base = (opts?.baseUrl || "https://www.mgstage.com").replace(/\/$/, "");
  const cid = code.replace(/-/g, "").toLowerCase();
  const url = `${base}/product/product_detail/${encodeURIComponent(code)}/`;
  const html = await fetchText(url, {
    referer: `${base}/`,
  });
  if (/お探しのページ|404|Not Found/i.test(html) && !/og:title/i.test(html)) {
    // 再试无横杠
    const url2 = `${base}/product/product_detail/${encodeURIComponent(code.toUpperCase())}/`;
    const html2 = await fetchText(url2, { referer: `${base}/` });
    return parseMg(html2, code, url2);
  }
  return parseMg(html, code, url);
}

function parseMg(html: string, code: string, url: string): PartialMeta {
  if (/お探しのページ|404/i.test(html) && !/og:title/i.test(html)) {
    throw new Error("mgstage not found");
  }
  const title = cleanTitle(pickOgTitle(html), code);
  const langs = splitTitleLang(title);
  const actresses = uniqNames(
    collectByRe(
      html,
      /href=["'][^"']*\/search\/c_actress\/[^"']+["'][^>]*>([^<]+)</gi,
    ),
  );
  let cover = pickOgImage(html);
  if (cover) cover = absUrl(cover, url);
  return {
    ...langs,
    actresses,
    cover_url: cover,
    source: "mgstage",
  };
}

/** FC2 Hub（现域名 javten.com，原 fc2hub.com；对齐 MDCx） */
export async function scrapeFc2Hub(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const m = code.match(/FC2[-_]?PPV[-_]?(\d+)/i) || code.match(/FC2[-_]?(\d+)/i);
  if (!m) throw new Error("not fc2 code");
  const id = m[1];
  const base = (opts?.baseUrl || "https://javten.com").replace(/\/$/, "");
  const url = `${base}/search?kw=${encodeURIComponent(id)}`;
  const search = await fetchText(url, { referer: `${base}/` });

  // MDCx：匹配含 id{number} 的链接，并跳过 /tw/ /ko/ /en/
  const hrefs = [
    ...search.matchAll(
      new RegExp(`(?:href|content)=["']([^"']*id${id}[^"']*)["']`, "gi"),
    ),
  ].map((x) => x[1]);
  const href =
    hrefs.find((h) => !/\/(tw|ko|en)\//i.test(h)) ||
    hrefs[0] ||
    search.match(
      new RegExp(`href=["']([^"']*${id}[^"']*)["']`, "i"),
    )?.[1] ||
    search.match(/href=["']([^"']*\/(?:video|id)[^"']+)["']/i)?.[1];
  if (!href) throw new Error("fc2hub no result");

  const detailUrl = absUrl(href, base);
  const html = await fetchText(detailUrl, { referer: url });

  // 标题：优先 h1 第二段（MDCx），再退 og:title
  const h1s = [...html.matchAll(/<h1[^>]*>([\s\S]*?)<\/h1>/gi)].map((x) =>
    stripTags(x[1]),
  );
  const h1Title =
    h1s.length >= 2
      ? h1s[1]
      : h1s.find((t) => t && !/^FC2/i.test(t)) || h1s[0] || "";
  const title = cleanTitle(h1Title || pickOgTitle(html), code);
  if (!title) throw new Error("fc2hub no title");
  const langs = splitTitleLang(title);

  // 封面：fancybox gallery → og:image
  let cover =
    html.match(
      /<a[^>]+data-fancybox=["']gallery["'][^>]+href=["']([^"']+)["']/i,
    )?.[1] ||
    html.match(
      /href=["']([^"']+)["'][^>]+data-fancybox=["']gallery["']/i,
    )?.[1] ||
    pickOgImage(html);
  if (cover) {
    if (cover.startsWith("//")) cover = `https:${cover}`;
    cover = absUrl(cover, detailUrl);
  }
  if (!cover) throw new Error("fc2hub no cover");

  return {
    ...langs,
    actresses: [],
    cover_url: cover,
    source: "fc2_hub",
  };
}

/** Caribbeancom（Carib）— 官网 EUC-JP */
export async function scrapeCarib(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  // 典型 010120-001 或 carib-xxx
  const m =
    code.match(/^(\d{6})[-_](\d{3})$/) || code.match(/^CARIB[-_]?(.+)$/i);
  if (!m) throw new Error("not carib code");
  const key = m[0].includes("CARIB") ? m[1] : `${m[1]}-${m[2]}`;
  const base = (opts?.baseUrl || "https://www.caribbeancom.com").replace(
    /\/$/,
    "",
  );
  const url = `${base}/moviepages/${key}/index.html`;
  // caribbeancom 固定 EUC-JP；强制解码避免代理剥掉 charset 后又乱码
  const html = await fetchText(url, {
    referer: `${base}/`,
    forceCharset: "euc-jp",
  });
  if (/404|見つかりません/i.test(html) && !/og:title|<\/title>/i.test(html)) {
    throw new Error("carib not found");
  }
  const title = cleanTitle(pickOgTitle(html), code);
  if (title && !/[\u3040-\u30ff\u4e00-\u9fff]/.test(title)) {
    throw new Error("carib title encoding broken");
  }
  const langs = splitTitleLang(title);
  const actresses = uniqNames(
    collectByRe(html, /href=["'][^"']*\/model\/[^"']+["'][^>]*>([^<]+)</gi),
  );
  let cover = `${base}/moviepages/${key}/images/l_l.jpg`;
  const og = pickOgImage(html);
  if (og) cover = absUrl(og, url);
  return {
    ...langs,
    actresses,
    cover_url: cover,
    source: "carib",
  };
}

/** Avbase */
export async function scrapeAvbase(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const base = (opts?.baseUrl || "https://www.avbase.net").replace(/\/$/, "");
  const searchUrl = `${base}/works?q=${encodeURIComponent(code)}`;
  const search = await fetchText(searchUrl, { referer: `${base}/` });
  const href =
    search.match(
      new RegExp(
        `href=["']([^"']*/works/[^"']+)["'][^>]*>[\\s\\S]{0,120}?${code.replace(/-/g, "[-]?")}`,
        "i",
      ),
    )?.[1] ||
    search.match(/href=["']([^"']*\/works\/[^"']+)["']/i)?.[1];
  if (!href) throw new Error("avbase no result");
  const detailUrl = absUrl(href, base);
  const html = await fetchText(detailUrl, { referer: searchUrl });
  const title = cleanTitle(pickOgTitle(html), code);
  const langs = splitTitleLang(title);
  const actresses = uniqNames(
    collectByRe(html, /href=["'][^"']*\/talents\/[^"']+["'][^>]*>([^<]+)</gi),
  );
  let cover = pickOgImage(html);
  if (cover) cover = absUrl(cover, detailUrl);
  return {
    ...langs,
    actresses,
    cover_url: cover,
    source: "avbase",
  };
}

/** 通用 og 刮削（国产站等） */
export async function scrapeByPath(
  code: string,
  opts: {
    baseUrl: string;
    source: string;
    paths: string[];
    actressRe?: RegExp;
  },
): Promise<PartialMeta> {
  const base = opts.baseUrl.replace(/\/$/, "");
  let lastErr = "";
  for (const p of opts.paths) {
    const url = `${base}${p.replace("{code}", encodeURIComponent(code)).replace("{slug}", code.toLowerCase())}`;
    try {
      const html = await fetchText(url, { referer: `${base}/` });
      if (/404|找不到|Not Found|页面不存在/i.test(html) && !/og:title/i.test(html)) {
        lastErr = "not found";
        continue;
      }
      const title = cleanTitle(pickOgTitle(html), code);
      if (!title && !pickOgImage(html)) {
        lastErr = "empty";
        continue;
      }
      const langs = splitTitleLang(title);
      const actresses = opts.actressRe
        ? uniqNames(collectByRe(html, opts.actressRe))
        : [];
      let cover = pickOgImage(html);
      if (cover) cover = absUrl(cover, url);
      return {
        ...langs,
        actresses,
        cover_url: cover,
        source: opts.source,
      };
    } catch (err) {
      lastErr = err instanceof Error ? err.message : String(err);
    }
  }
  throw new Error(`${opts.source} failed: ${lastErr}`);
}

export async function scrapeMadou(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  return scrapeByPath(code, {
    baseUrl: opts?.baseUrl || "https://madou.club",
    source: "madou",
    paths: [`/${code}`, `/video/${code}`, `/search?q={code}`],
  });
}

export async function scrapeMadouqu(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  return scrapeByPath(code, {
    baseUrl: opts?.baseUrl || "https://madouqu.com",
    source: "madouqu",
    paths: [`/${code}`, `/video/{slug}`, `/?s={code}`],
  });
}

export async function scrapeHbox(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  return scrapeByPath(code, {
    baseUrl: opts?.baseUrl || "https://hbox.jp",
    source: "hbox_jp",
    paths: [`/search?q={code}`, `/works/{code}`],
  });
}

export async function scrapeXhs(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  return scrapeByPath(code, {
    baseUrl: opts?.baseUrl || "https://www.xiaohongshu.com",
    source: "xiao_huang_shu",
    paths: [`/search_result?keyword={code}`],
  });
}

/** ThePornDB 需要 API Key，无 key 时跳过 */
export async function scrapeTheporndb(
  _code: string,
  _opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const key = (process.env.THEPORNDB_API_KEY || "").trim();
  if (!key) throw new Error("THEPORNDB_API_KEY not set");
  throw new Error("theporndb not configured");
}

/**
 * FD2 / fd2ppv.cc — FC2 资料站（封面优先：样图多为横版）
 * 需 FlareSolverr；封面在 .work-original-photos 文本块里
 */
export async function scrapeFd2ppv(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const m = code.match(/FC2[-_]?PPV[-_]?(\d+)/i) || code.match(/FC2[-_]?(\d+)/i);
  if (!m) throw new Error("not fc2 code");
  const id = m[1];
  const base = (opts?.baseUrl || "https://fd2ppv.cc").replace(/\/$/, "");
  const url = `${base}/articles/${id}`;
  const html = await fetchText(url, {
    referer: `${base}/`,
    timeoutMs: 60000,
  });
  if (
    /Too many requests|Just a moment|cf-browser-verification/i.test(html) &&
    html.length < 5000
  ) {
    throw new Error("fd2ppv blocked");
  }
  if (/作品が見つかりません|ページが見つかりません|404 Not Found/i.test(html)) {
    throw new Error("fd2ppv not found");
  }

  const photoBlock =
    html.match(
      /class=["'][^"']*work-original-photos[^"']*["'][^>]*>([\s\S]*?)<\/div>/i,
    )?.[1] ||
    html.match(
      /class=["'][^"']*work-photos[^"']*["'][^>]*>([\s\S]*?)<\/div>/i,
    )?.[1] ||
    "";
  const photos = [
    ...photoBlock.matchAll(/(https?:\/\/[^\s"'<>]+\.(?:jpg|jpeg|png|webp|avif))/gi),
  ].map((x) => x[1]);
  // 封面优先：FC2 CDN 横版样图 > 站内托管图
  const cover =
    photos.find((u) => /contents-thumbnail|contents\.fc2\.com|storage\d*\.contents/i.test(u)) ||
    photos.find((u) => /xximgs\.cc|\/uploads\//i.test(u)) ||
    photos[0] ||
    null;
  if (!cover) throw new Error("fd2ppv no cover");

  const brief = stripTags(
    html.match(/class=["']work-brief["'][^>]*>([\s\S]*?)<\/div>/i)?.[1] || "",
  ).trim();
  const metaDesc = html
    .match(/<meta[^>]+name=["']description["'][^>]+content=["']([^"']+)["']/i)?.[1]
    ?.trim();
  const title = cleanTitle(brief || metaDesc || null, code);
  if (!title) throw new Error("fd2ppv no title");
  const langs = splitTitleLang(title);

  const actresses = uniqNames(
    collectByRe(html, /href=["']\/actresses\/\d+["'][^>]*>([^<]+)</gi),
  );

  return {
    ...langs,
    actresses,
    cover_url: cover,
    source: "fd2ppv",
  };
}

/** FC2 官方/镜像简单封面尝试 */
export async function scrapeFc2(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const m = code.match(/FC2[-_]?PPV[-_]?(\d+)/i) || code.match(/FC2[-_]?(\d+)/i);
  if (!m) throw new Error("not fc2 code");
  const id = m[1];
  const base = (opts?.baseUrl || "https://adult.contents.fc2.com").replace(
    /\/$/,
    "",
  );
  const url = `${base}/article/${id}/`;
  const html = await fetchText(url, { referer: `${base}/` });
  // 勿匹配裸 "404"：SVG path 坐标（如 13.404）会误杀有效商品页
  if (
    /未找到您要找的商品|お探しの商品は見つかりません|この商品は販売を終了/i.test(
      html,
    )
  ) {
    throw new Error("fc2 not found");
  }
  const title = cleanTitle(pickOgTitle(html), code);
  if (
    !title ||
    /未找到您要找的商品|お探しの商品は見つかりません|販売を終了/i.test(title)
  ) {
    throw new Error("fc2 not found");
  }
  const langs = splitTitleLang(title);
  let cover = pickOgImage(html);
  if (cover) cover = absUrl(cover, url);
  if (!cover) throw new Error("fc2 no cover");
  return {
    ...langs,
    actresses: [],
    cover_url: cover,
    source: "fc2",
  };
}
