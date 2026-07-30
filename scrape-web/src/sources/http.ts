import { fetch as undiciFetch } from "undici";

import {
  fetchViaFlareSolverr,
  getFlareSolverrUrl,
} from "../flaresolverr.js";
import { getRequestProfile, resolveFetchOptions } from "../httpContext.js";

export type PartialMeta = {
  title_zh?: string | null;
  title_ja?: string | null;
  actresses?: string[];
  cover_url?: string | null;
  source?: string;
};

/** Content-Type / meta charset → WHATWG 标签（给 TextDecoder） */
function normalizeCharset(raw: string | null | undefined): string {
  const c = String(raw || "")
    .toLowerCase()
    .replace(/['"]/g, "")
    .trim();
  if (!c || /utf-?8/i.test(c)) return "utf-8";
  if (/euc-?jp|x-euc-jp/i.test(c)) return "euc-jp";
  if (/shift[_-]?jis|sjis|windows-31j|csshiftjis|x-sjis/i.test(c)) {
    return "shift_jis";
  }
  if (/iso-2022-jp/i.test(c)) return "iso-2022-jp";
  if (/gbk|gb2312|gb18030/i.test(c)) return "gbk";
  if (/big5/i.test(c)) return "big5";
  if (/euc-?kr|korean/i.test(c)) return "euc-kr";
  return c;
}

function charsetFromHeadersAndBody(
  contentType: string | null,
  buf: Buffer,
): string {
  const fromHeader = contentType?.match(/charset\s*=\s*["']?([^\s;"']+)/i)?.[1];
  if (fromHeader) return normalizeCharset(fromHeader);
  const head = buf.subarray(0, Math.min(buf.length, 4096)).toString("latin1");
  const fromMeta =
    head.match(/<meta[^>]+charset\s*=\s*["']?\s*([^"'>\s/]+)/i)?.[1] ||
    head.match(
      /<meta[^>]+content\s*=\s*["'][^"']*charset\s*=\s*([^"'\s;]+)/i,
    )?.[1];
  return normalizeCharset(fromMeta || "utf-8");
}

async function fetchTextOnce(
  url: string,
  opts?: {
    referer?: string;
    timeoutMs?: number;
    forceCharset?: string;
  },
): Promise<string> {
  const profile = getRequestProfile();
  const resolved = resolveFetchOptions({
    referer: opts?.referer || new URL(url).origin + "/",
    timeoutMs: opts?.timeoutMs,
  });

  // mdc-ng 关键：CF 站走 FlareSolverr，否则易 403
  if (profile.useFlareSolverr && getFlareSolverrUrl()) {
    return fetchViaFlareSolverr(url, {
      timeoutMs: Math.max(resolved.timeoutMs, 30000),
      useProxy: profile.proxyMode !== "off",
      cookie: profile.cookie,
    });
  }

  const res = await undiciFetch(url, {
    headers: resolved.headers,
    redirect: "follow",
    signal: AbortSignal.timeout(resolved.timeoutMs),
    ...(resolved.dispatcher ? { dispatcher: resolved.dispatcher } : {}),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${url}`);
  const buf = Buffer.from(await res.arrayBuffer());
  const label = normalizeCharset(
    opts?.forceCharset ||
      charsetFromHeadersAndBody(res.headers.get("content-type"), buf),
  );
  try {
    return new TextDecoder(label).decode(new Uint8Array(buf));
  } catch {
    return buf.toString("utf8");
  }
}

/** 使用 undici.fetch；自动带上当前源的 Cookie/UA/代理/重试 */
export async function fetchText(
  url: string,
  opts?: {
    referer?: string;
    timeoutMs?: number;
    /** 强制 charset（如 caribbeancom 的 euc-jp） */
    forceCharset?: string;
  },
): Promise<string> {
  const { retry } = resolveFetchOptions({ timeoutMs: opts?.timeoutMs });
  let lastErr: unknown;
  for (let i = 0; i <= retry; i++) {
    try {
      return await fetchTextOnce(url, opts);
    } catch (err) {
      lastErr = err;
      if (i < retry) {
        await new Promise((r) => setTimeout(r, 300 + i * 200));
      }
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
}

export { undiciFetch };

export function decodeHtml(text: string): string {
  return text
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) =>
      String.fromCharCode(parseInt(n, 16)),
    );
}

export function stripTags(html: string): string {
  return decodeHtml(html.replace(/<[^>]+>/g, " "))
    .replace(/\s+/g, " ")
    .trim();
}

export function uniqNames(list: string[]): string[] {
  const junk = new Set([
    "有碼",
    "有码",
    "無碼",
    "无码",
    "歐美",
    "欧美",
    "國產",
    "国产",
    "素人",
    "動漫",
    "动漫",
    "女優",
    "女优",
    "演員",
    "演员",
    "全部",
    "首頁",
    "首页",
    "搜索",
    "登錄",
    "登录",
    "註冊",
    "注册",
  ]);
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of list) {
    const name = raw.replace(/\s+/g, " ").trim();
    if (!name || junk.has(name) || name.length > 24) continue;
    if (/^(FC2|DMM|JAV|AV|SEX|DVD|BD)$/i.test(name)) continue;
    if (seen.has(name)) continue;
    seen.add(name);
    out.push(name);
  }
  return out;
}
