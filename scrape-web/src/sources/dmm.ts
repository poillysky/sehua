import { downloadToCover } from "../covers.js";
import { normalizeCode } from "../db.js";
import { coverRelPath } from "../storageLayout.js";
import type { CodeKind } from "./registry.js";
import { fetchText, stripTags, undiciFetch, type PartialMeta } from "./http.js";

export function toDmmCid(code: string): string | null {
  const normalized = normalizeCode(code);
  if (!normalized) return null;
  if (/^FC2/i.test(normalized)) return null;
  const m = normalized.match(/^([A-Z]{2,10})-(\d{2,6})$/);
  if (!m) return null;
  return `${m[1].toLowerCase()}${m[2]}`;
}

function dmmCoverCandidates(cid: string): string[] {
  const out: string[] = [];
  const push = (c: string) => {
    out.push(`https://pics.dmm.co.jp/digital/video/${c}/${c}pl.jpg`);
    out.push(`https://pics.dmm.co.jp/digital/video/${c}/${c}ps.jpg`);
  };
  const m = cid.match(/^([a-z]+)(\d+)$/i);
  const variants: string[] = [];
  if (m) {
    const prefix = m[1].toLowerCase();
    const num = m[2];
    // 先试加零（如 ssis00240），短 cid 常 200 跳转到 now_printing 占位图
    for (const width of [5, 3]) {
      const padded = `${prefix}${num.padStart(width, "0")}`;
      if (!variants.includes(padded)) variants.push(padded);
    }
  }
  if (!variants.includes(cid)) variants.push(cid);
  const with1 = `1${cid}`;
  if (!variants.includes(with1)) variants.push(with1);
  for (const c of variants) push(c);
  return out;
}

function isDmmPlaceholder(url: string, bytesHint?: number): boolean {
  if (/now_printing/i.test(url)) return true;
  if (bytesHint != null && bytesHint > 0 && bytesHint < 30000) return true;
  return false;
}

export async function scrapeDmmMeta(
  code: string,
  opts?: { baseUrl?: string },
): Promise<PartialMeta> {
  const cid = toDmmCid(code);
  if (!cid) throw new Error("cannot map to DMM cid");

  const site = (opts?.baseUrl || "https://www.dmm.co.jp").replace(/\/$/, "");
  const referer = `${site}/`;
  let cover_url: string | null = null;
  let lastErr = "";
  for (const url of dmmCoverCandidates(cid)) {
    try {
      const head = await undiciFetch(url, {
        method: "GET",
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
          Referer: referer,
          Range: "bytes=0-2047",
        },
        redirect: "follow",
        signal: AbortSignal.timeout(8000),
      });
      if (!head.ok && head.status !== 206) {
        lastErr = `HTTP ${head.status}`;
        continue;
      }
      const finalUrl = String(head.url || url);
      const cl = Number(head.headers.get("content-length") || 0);
      // Content-Range: bytes 0-2047/19378 → 取总分大小
      const rangeTotal = Number(
        (head.headers.get("content-range") || "").split("/")[1] || 0,
      );
      const sizeHint = rangeTotal || cl;
      if (isDmmPlaceholder(finalUrl, sizeHint)) {
        lastErr = "dmm now_printing placeholder";
        continue;
      }
      cover_url = url;
      break;
    } catch (err) {
      lastErr = err instanceof Error ? err.message : String(err);
    }
  }
  if (!cover_url) throw new Error(lastErr || "dmm cover missing");

  let title_ja: string | null = null;
  try {
    const detail = `${site}/digital/videoa/-/detail/=/cid=${cid}/`;
    const html = await fetchText(detail, { referer });
    const og =
      html.match(/property=["']og:title["']\s+content=["']([^"']+)["']/i)?.[1] ||
      html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)?.[1];
    if (og) title_ja = stripTags(og).replace(/\s*[|｜].*$/, "").trim();
  } catch {
    /* title optional */
  }

  return {
    title_ja,
    cover_url,
    source: "dmm",
  };
}

export async function downloadCoverFromUrl(
  code: string,
  url: string,
  referer: string,
  opts?: { overwrite?: boolean; kind?: CodeKind },
): Promise<string> {
  const rel = coverRelPath(code, opts?.kind);
  return downloadToCover(url, rel, referer, { ...opts, code });
}
