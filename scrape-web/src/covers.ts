import fs from "node:fs/promises";
import path from "node:path";
import { createWriteStream } from "node:fs";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import { fetch as undiciFetch } from "undici";
import sharp from "sharp";

import { resolveFetchOptions } from "./httpContext.js";
import { getCoversDir } from "./paths.js";
import {
  coverRelCandidates,
  coverRelPath,
  safeCodeFilename,
} from "./storageLayout.js";
import type { CodeKind } from "./sources/registry.js";

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36";

export async function ensureCoversDir(): Promise<void> {
  await fs.mkdir(getCoversDir(), { recursive: true });
}

/** @deprecated 用 coverRelPath；保留给旧调用 */
export function safeCoverFilename(code: string, ext = ".jpg"): string {
  return safeCodeFilename(code, ext);
}

export function coverPublicPath(relPosix: string): string {
  const rel = String(relPosix || "")
    .replace(/\\/g, "/")
    .replace(/^\/+/, "");
  return `/covers/${rel}`;
}

/**
 * 下载封面到 板块/厂牌/番号.jpg；返回公开路径 /covers/...
 * 有码横图会裁右半幅海报；无码/国产保留整图不裁。
 */
export async function downloadToCover(
  url: string,
  relPosix: string,
  referer: string,
  opts?: { overwrite?: boolean; code?: string; kind?: CodeKind },
): Promise<string> {
  await ensureCoversDir();
  const rel = String(relPosix || "")
    .replace(/\\/g, "/")
    .replace(/^\/+/, "");
  const target = path.join(getCoversDir(), ...rel.split("/"));
  const tmp = `${target}.part`;

  await fs.mkdir(path.dirname(target), { recursive: true });
  await fs.unlink(tmp).catch(() => undefined);
  if (opts?.overwrite) {
    await fs.unlink(target).catch(() => undefined);
  }

  try {
    const resolved = resolveFetchOptions({
      referer,
      timeoutMs: Number(process.env.COVER_FETCH_TIMEOUT_MS || 15000),
    });
    const headers = {
      ...resolved.headers,
      Accept: "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
      Referer: referer,
      "User-Agent": resolved.headers["User-Agent"] || UA,
    };
    const res = await undiciFetch(url, {
      headers,
      redirect: "follow",
      signal: AbortSignal.timeout(resolved.timeoutMs),
      ...(resolved.dispatcher ? { dispatcher: resolved.dispatcher } : {}),
    });
    if (!res.ok) {
      throw new Error(`cover HTTP ${res.status}`);
    }
    if (/now_printing/i.test(String(res.url || url))) {
      throw new Error("cover placeholder (now_printing)");
    }
    const ctype = (res.headers.get("content-type") || "").toLowerCase();
    if (ctype && !ctype.includes("image") && !ctype.includes("octet-stream")) {
      throw new Error(`not image content-type: ${ctype}`);
    }
    if (!res.body) {
      throw new Error("empty body");
    }
    const nodeStream = Readable.fromWeb(
      res.body as import("node:stream/web").ReadableStream,
    );
    await pipeline(nodeStream, createWriteStream(tmp));
    const stat = await fs.stat(tmp);
    if (stat.size < 8000) {
      throw new Error(`cover too small: ${stat.size}`);
    }
    const head = Buffer.alloc(Math.min(64 * 1024, stat.size));
    const fh = await fs.open(tmp, "r");
    try {
      await fh.read(head, 0, head.length, 0);
    } finally {
      await fh.close();
    }
    const dim = readJpegSize(head);
    if (dim && (dim.w < 200 || dim.h < 280)) {
      throw new Error(`cover too tiny: ${dim.w}x${dim.h}`);
    }
    if (stat.size < 40000 && dim && dim.w >= 400 && dim.h >= 500) {
      throw new Error(
        `cover placeholder suspected: ${stat.size}B ${dim.w}x${dim.h}`,
      );
    }
    // 有码 DMM 式「左封底+右封面」才裁右半；无码/国产整图保留
    const skipCrop =
      opts?.kind === "uncensored" ||
      opts?.kind === "chinese" ||
      opts?.kind === "fc2" ||
      opts?.kind === "western" ||
      /caribbeancom\.com|1pondo\.|10musume\.|pacopacomama|heyzo\.|tokyo-?hot/i.test(
        url,
      );
    if (!skipCrop) {
      await cropToRightPoster(tmp);
    }
    await fs.unlink(target).catch(() => undefined);
    await fs.rename(tmp, target);

    // 新分级写入成功后，清掉旧扁平/其它候选，避免双份
    const codeHint =
      opts?.code ||
      path.basename(rel, path.extname(rel));
    for (const cand of coverRelCandidates(codeHint)) {
      if (cand === rel) continue;
      const old = path.join(getCoversDir(), ...cand.split("/"));
      await fs.unlink(old).catch(() => undefined);
    }

    return coverPublicPath(rel);
  } catch (err) {
    await fs.unlink(tmp).catch(() => undefined);
    throw err;
  }
}

/** 递归清理 *.part */
export async function cleanupCoverPartFiles(): Promise<number> {
  const root = getCoversDir();
  let n = 0;
  async function walk(dir: string) {
    let entries;
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const ent of entries) {
      const full = path.join(dir, ent.name);
      if (ent.isDirectory()) {
        await walk(full);
        continue;
      }
      if (!ent.name.toLowerCase().endsWith(".part")) continue;
      await fs.unlink(full).catch(() => undefined);
      n += 1;
    }
  }
  await walk(root);
  return n;
}

export async function cropToRightPoster(filePath: string): Promise<boolean> {
  const img = sharp(filePath);
  const meta = await img.metadata();
  const w = meta.width || 0;
  const h = meta.height || 0;
  if (!w || !h || w <= h) return false;
  const left = Math.floor(w / 2);
  const width = w - left;
  const out = `${filePath}.crop`;
  await sharp(filePath)
    .extract({ left, top: 0, width, height: h })
    .jpeg({ quality: 90 })
    .toFile(out);
  await fs.unlink(filePath).catch(() => undefined);
  await fs.rename(out, filePath);
  return true;
}

function readJpegSize(
  buf: Buffer,
): { w: number; h: number } | null {
  if (buf.length < 4 || buf[0] !== 0xff || buf[1] !== 0xd8) return null;
  let i = 2;
  while (i + 9 < buf.length) {
    if (buf[i] !== 0xff) break;
    const marker = buf[i + 1];
    if (marker === 0xd9 || marker === 0xda) break;
    const len = buf.readUInt16BE(i + 2);
    if (len < 2) break;
    if (
      marker === 0xc0 ||
      marker === 0xc1 ||
      marker === 0xc2 ||
      marker === 0xc3
    ) {
      const h = buf.readUInt16BE(i + 5);
      const w = buf.readUInt16BE(i + 7);
      return { w, h };
    }
    i += 2 + len;
  }
  return null;
}

async function firstExistingCoverAbs(
  code: string,
  kind?: CodeKind,
): Promise<{ abs: string; rel: string } | null> {
  const root = getCoversDir();
  for (const rel of coverRelCandidates(code, kind)) {
    const abs = path.join(root, ...rel.split("/"));
    try {
      const st = await fs.stat(abs);
      if (st.isFile() && st.size >= 8000) return { abs, rel };
    } catch {
      /* try next */
    }
  }
  return null;
}

/** 本地是否已有可用正式封面（分级或旧扁平；不含 .part） */
export async function hasLocalCover(
  code: string,
  kind?: CodeKind,
): Promise<boolean> {
  return Boolean(await firstExistingCoverAbs(code, kind));
}

/** 本地封面绝对路径（若存在） */
export async function localCoverAbsPath(
  code: string,
  kind?: CodeKind,
): Promise<string | null> {
  const hit = await firstExistingCoverAbs(code, kind);
  return hit?.abs || null;
}

/** 公开 URL 相对路径；有文件用实际路径，否则给新分级路径 */
export async function resolveCoverPublicRel(
  code: string,
  kind?: CodeKind,
): Promise<string> {
  const hit = await firstExistingCoverAbs(code, kind);
  if (hit) return hit.rel;
  return coverRelPath(code, kind);
}
