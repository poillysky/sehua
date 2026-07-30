import { undiciFetch } from "./sources/http.js";

/**
 * 日文片名 → 简体中文（Google 公开翻译接口，走 undici 代理）。
 * 仅作中文源失败时的兜底。
 */
export async function translateJaToZh(
  text: string,
): Promise<string | null> {
  const q = String(text || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 400);
  if (!q) return null;
  // 已是中文且无假名则不必翻
  if (/[\u4e00-\u9fff]/.test(q) && !/[\u3040-\u30ff]/.test(q)) return q;

  const url = new URL("https://translate.googleapis.com/translate_a/single");
  url.searchParams.set("client", "gtx");
  url.searchParams.set("sl", "ja");
  url.searchParams.set("tl", "zh-CN");
  url.searchParams.set("dt", "t");
  url.searchParams.set("q", q);

  try {
    const res = await undiciFetch(url.toString(), {
      method: "GET",
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        Accept: "application/json,*/*",
      },
      signal: AbortSignal.timeout(12000),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as unknown;
    const parts = Array.isArray(data) && Array.isArray(data[0]) ? data[0] : [];
    const out = parts
      .map((item: unknown) =>
        Array.isArray(item) && typeof item[0] === "string" ? item[0] : "",
      )
      .join("")
      .trim();
    if (!out || out === q) return null;
    return out;
  } catch {
    return null;
  }
}

/** 女优名：只要中文（含汉字、无假名），去掉日文名 */
export function chineseOnlyNames(names: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of names) {
    const n = String(raw || "").trim();
    if (!n || n.length > 24) continue;
    if (/[\u3040-\u30ff]/.test(n)) continue; // 假名 → 日文
    if (!/[\u4e00-\u9fff]/.test(n)) continue;
    const key = n.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(n);
  }
  return out;
}
