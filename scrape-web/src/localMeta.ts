import fs from "node:fs/promises";
import path from "node:path";

import { localCoverAbsPath } from "./covers.js";
import {
  getCoversDirConfigured,
  getMetaDir,
  getMetaDirConfigured,
} from "./paths.js";
import { metaRelCandidates, metaRelPath } from "./storageLayout.js";
import type { CodeKind } from "./sources/registry.js";
import type { ScrapeResult } from "./scrape.js";

export async function ensureMetaDir(): Promise<void> {
  await fs.mkdir(getMetaDir(), { recursive: true });
}

/**
 * 刮削结果：meta/{板块}/{厂牌}/{番号}.json
 * 同时删掉旧扁平同名，避免重复。
 */
export async function writeLocalMeta(
  scraped: ScrapeResult,
): Promise<{ metaPath: string; coverAbs: string | null }> {
  await ensureMetaDir();
  const kind = (scraped.kind as CodeKind | undefined) || undefined;
  const rel = metaRelPath(scraped.code, kind);
  const metaPath = path.join(getMetaDir(), ...rel.split("/"));
  await fs.mkdir(path.dirname(metaPath), { recursive: true });

  const coverAbs = scraped.cover_path
    ? await localCoverAbsPath(scraped.code, kind)
    : null;
  const coverFile = scraped.cover_path
    ? scraped.cover_path.replace(/^\/covers\//, "")
    : null;

  const payload = {
    code: scraped.code,
    kind: scraped.kind ?? null,
    title: scraped.title,
    title_zh: scraped.title_zh,
    title_ja: scraped.title_ja,
    actresses: scraped.actresses,
    cover_path: scraped.cover_path,
    cover_file: coverFile
      ? `${getCoversDirConfigured()}/${coverFile}`
      : null,
    cover_source: scraped.cover_source,
    sources: scraped.sources,
    status: scraped.status,
    error: scraped.error ?? null,
    scraped_at: new Date().toISOString(),
    covers_dir: getCoversDirConfigured(),
    meta_dir: getMetaDirConfigured(),
    layout: rel,
  };

  const tmp = `${metaPath}.part`;
  await fs.writeFile(tmp, JSON.stringify(payload, null, 2), "utf8");
  await fs.unlink(metaPath).catch(() => undefined);
  await fs.rename(tmp, metaPath);

  for (const cand of metaRelCandidates(scraped.code, kind)) {
    if (cand === rel) continue;
    const old = path.join(getMetaDir(), ...cand.split("/"));
    await fs.unlink(old).catch(() => undefined);
  }

  return { metaPath, coverAbs };
}
