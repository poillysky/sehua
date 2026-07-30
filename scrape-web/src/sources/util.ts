import { stripTags } from "./http.js";

export function isLikelyChinese(title: string): boolean {
  if (!/[\u4e00-\u9fff]/.test(title)) return false;
  if (/[\u3040-\u30ff]/.test(title)) return false;
  return true;
}

export function cleanTitle(
  raw: string | null | undefined,
  code?: string,
): string | null {
  if (!raw) return null;
  let t = stripTags(raw)
    .replace(
      /\s*[-–—|｜]\s*(JavDB|JavBus|Airav|MISSAV|7MM|AVSOX|AVMOO|JAVLibrary).*$/i,
      "",
    )
    // 加勒比等官网 title：片名 | 無修正アダルト動画 カリビアンコム
    .replace(
      /\s*[|｜][^|｜]*(カリビアンコム|Caribbeancom|一本道|1pondo\.tv|HEYZO).*$/i,
      "",
    )
    .replace(/\s+/g, " ")
    .trim();
  if (code) {
    t = t.replace(new RegExp(`^${code}\\s*[|：:\\-]?\\s*`, "i"), "").trim();
  }
  // 搜索页 / 列表页标题不算片名
  if (
    /搜索结果|搜尋結果|search\s*result|の検索結果|找到\s*\d+|共\s*\d+\s*条/i.test(
      t,
    )
  ) {
    return null;
  }
  if (code && new RegExp(`^[「『]?${code}[」』]?$`, "i").test(t)) return null;
  return t || null;
}

export function splitTitleLang(title: string | null): {
  title_zh: string | null;
  title_ja: string | null;
} {
  if (!title) return { title_zh: null, title_ja: null };
  if (isLikelyChinese(title)) return { title_zh: title, title_ja: null };
  return { title_zh: null, title_ja: title };
}

/** 介质 / 版本后缀（中日英） */
const MEDIA_SUFFIX_RE =
  /\s*[（(【\[]?\s*(?:蓝光(?:光盘|碟|版)?|藍光(?:光碟|版)?|ブルーレイ(?:ディスク)?|Blu-?ray|BD|DVD|4K|UHD|HD|高清|無碼流出|破解版|中文字幕|字幕版|完整版)\s*[）)】\]]?\s*$/gi;

/**
 * 定稿中文片名：去掉介质后缀、末尾女优名。
 */
export function finalizeTitleZh(
  raw: string | null | undefined,
  actresses: string[] = [],
): string | null {
  if (!raw) return null;
  let t = String(raw).replace(/\s+/g, " ").trim();
  if (!t) return null;

  // 反复剥介质后缀
  for (let i = 0; i < 3; i++) {
    const next = t.replace(MEDIA_SUFFIX_RE, "").trim();
    if (next === t) break;
    t = next;
  }

  // 句号后若只剩 1～3 个短中文词（女优名），整段去掉
  t = t
    .replace(/[。．.]\s*(?:[\u4e00-\u9fff]{2,5}\s*){1,3}$/u, "")
    .trim();

  // 末尾女优名（按长度降序，避免短名误伤）
  const names = [...actresses]
    .map((n) => String(n || "").trim())
    .filter((n) => n.length >= 2)
    .sort((a, b) => b.length - a.length);

  for (let round = 0; round < 6; round++) {
    let changed = false;
    for (const name of names) {
      const esc = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      // 末尾：空格/顿号/逗号/、分隔的女优名
      const re = new RegExp(
        `(?:\\s*[、,，/｜|]?\\s*${esc})+\\s*$`,
        "u",
      );
      const next = t.replace(re, "").trim();
      if (next !== t && next.length >= 4) {
        t = next;
        changed = true;
      }
    }
    if (!changed) break;
  }

  t = t.replace(/[、,，\s/｜|。．.]+$/g, "").trim();
  return t || null;
}

export function pickMeta(html: string, ...patterns: RegExp[]): string | null {
  for (const re of patterns) {
    const m = html.match(re);
    if (m?.[1]) return m[1];
  }
  return null;
}

export function pickOgTitle(html: string): string | null {
  return pickMeta(
    html,
    /property=["']og:title["']\s+content=["']([^"']+)["']/i,
    /content=["']([^"']+)["']\s+property=["']og:title["']/i,
    /<title[^>]*>([\s\S]*?)<\/title>/i,
  );
}

export function pickOgImage(html: string): string | null {
  return pickMeta(
    html,
    /property=["']og:image["']\s+content=["']([^"']+)["']/i,
    /content=["']([^"']+)["']\s+property=["']og:image["']/i,
  );
}

/** 番号须出现在 og:title / 页面标题，避免相关推荐串片 */
export function pageMentionsCode(html: string, code: string): boolean {
  const esc = code
    .replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    .replace(/-/g, "[-_]?");
  const re = new RegExp(esc, "i");
  const title = pickOgTitle(html) || "";
  if (re.test(title)) return true;
  const h1 = stripTags(html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)?.[1] || "");
  if (re.test(h1)) return true;
  return false;
}

export function absUrl(href: string, base: string): string {
  try {
    return new URL(href, base).toString();
  } catch {
    return href;
  }
}

export function collectByRe(html: string, re: RegExp): string[] {
  const out: string[] = [];
  let m: RegExpExecArray | null;
  const flags = re.flags.includes("g") ? re.flags : `${re.flags}g`;
  const r = new RegExp(re.source, flags);
  while ((m = r.exec(html)) !== null) {
    const name = stripTags(m[1] || "").trim();
    if (name) out.push(name);
  }
  return out;
}
