/**
 * 将旧扁平 covers/CODE.jpg、meta/CODE.json
 * 迁移到 板块/厂牌/CODE.*，并更新 av_metadata.cover_path。
 *
 *   cd scrape-web && npx tsx src/migrateFlatLayout.ts
 *   npx tsx src/migrateFlatLayout.ts --dry-run
 */
import fs from "node:fs/promises";
import path from "node:path";
import { config as loadEnv } from "dotenv";

import { readConfig } from "./config.js";
import { ensureSchema, normalizeCode, pool } from "./db.js";
import {
  applyDataDirsFromConfig,
  getCoversDir,
  getMetaDir,
} from "./paths.js";
import { coverRelPath, metaRelPath } from "./storageLayout.js";
import { detectCodeKind } from "./sources/registry.js";

loadEnv();

const dryRun = process.argv.includes("--dry-run");

async function moveFile(from: string, to: string): Promise<"moved" | "skip" | "exists"> {
  try {
    await fs.access(from);
  } catch {
    return "skip";
  }
  try {
    await fs.access(to);
    // 目标已有：删源扁平，保留分级
    if (!dryRun) await fs.unlink(from).catch(() => undefined);
    return "exists";
  } catch {
    /* target missing */
  }
  if (dryRun) return "moved";
  await fs.mkdir(path.dirname(to), { recursive: true });
  await fs.rename(from, to);
  return "moved";
}

async function migrateDir(
  root: string,
  kind: "cover" | "meta",
): Promise<{ moved: number; existed: number; skipped: number }> {
  let moved = 0;
  let existed = 0;
  let skipped = 0;
  let entries: string[];
  try {
    entries = await fs.readdir(root);
  } catch {
    console.warn(`[migrate] dir missing: ${root}`);
    return { moved, existed, skipped };
  }

  for (const name of entries) {
    const abs = path.join(root, name);
    let st;
    try {
      st = await fs.stat(abs);
    } catch {
      skipped += 1;
      continue;
    }
    if (!st.isFile()) continue;

    const lower = name.toLowerCase();
    if (lower.endsWith(".part") || lower.endsWith(".crop")) {
      if (!dryRun) await fs.unlink(abs).catch(() => undefined);
      skipped += 1;
      continue;
    }

    let code = "";
    let destRel = "";
    if (kind === "cover" && /\.jpe?g$/i.test(name)) {
      code = normalizeCode(name.replace(/\.jpe?g$/i, ""));
      if (!code) {
        skipped += 1;
        continue;
      }
      destRel = coverRelPath(code, detectCodeKind(code));
    } else if (kind === "meta" && /\.json$/i.test(name)) {
      code = normalizeCode(name.replace(/\.json$/i, ""));
      if (!code) {
        skipped += 1;
        continue;
      }
      // meta 内若有 kind 字段优先
      let kindHint = detectCodeKind(code);
      try {
        const raw = await fs.readFile(abs, "utf8");
        const j = JSON.parse(raw) as { kind?: string; code?: string };
        if (j.code) code = normalizeCode(j.code) || code;
        const k = String(j.kind || "").toLowerCase();
        if (
          k === "av" ||
          k === "uncensored" ||
          k === "mgstage" ||
          k === "fc2" ||
          k === "chinese" ||
          k === "western"
        ) {
          kindHint = k;
        }
      } catch {
        /* ignore parse */
      }
      destRel = metaRelPath(code, kindHint);
    } else {
      skipped += 1;
      continue;
    }

    // 已在子目录里的不会出现在 root readdir 的「仅文件」——上面已 isFile only at root
    const dest = path.join(root, ...destRel.split("/"));
    if (path.resolve(abs) === path.resolve(dest)) {
      skipped += 1;
      continue;
    }

    const r = await moveFile(abs, dest);
    if (r === "moved") {
      moved += 1;
      console.log(`[migrate] ${kind} ${name} → ${destRel}`);
    } else if (r === "exists") {
      existed += 1;
      console.log(`[migrate] ${kind} ${name} 目标已存在，删扁平`);
    } else {
      skipped += 1;
    }
  }

  return { moved, existed, skipped };
}

async function updateDbCoverPaths(): Promise<number> {
  const { rows } = await pool.query<{ code: string; cover_path: string }>(
    `SELECT code, cover_path
     FROM av_metadata
     WHERE coalesce(cover_path, '') <> ''`,
  );
  let n = 0;
  for (const row of rows) {
    const code = normalizeCode(row.code);
    if (!code) continue;
    const cur = String(row.cover_path || "").replace(/\\/g, "/");
    // 已是分级：/covers/有码/ABF/xxx.jpg
    const parts = cur.replace(/^\/covers\//, "").split("/").filter(Boolean);
    if (parts.length >= 3) continue;

    const rel = coverRelPath(code, detectCodeKind(code));
    const next = `/covers/${rel}`;
    if (next === cur) continue;
    if (!dryRun) {
      await pool.query(
        `UPDATE av_metadata SET cover_path = $2, updated_at = NOW() WHERE code = $1`,
        [code, next],
      );
    }
    n += 1;
    console.log(`[migrate] db ${code}: ${cur} → ${next}`);
  }
  return n;
}

async function main() {
  const cfg = await readConfig();
  applyDataDirsFromConfig(cfg);
  await ensureSchema();

  const covers = getCoversDir();
  const meta = getMetaDir();
  console.log(
    `[migrate] covers=${covers} meta=${meta}${dryRun ? " (dry-run)" : ""}`,
  );

  const c = await migrateDir(covers, "cover");
  const m = await migrateDir(meta, "meta");
  const db = await updateDbCoverPaths();

  console.log(
    `[migrate] done covers moved=${c.moved} existed=${c.existed} skip=${c.skipped}`,
  );
  console.log(
    `[migrate] done meta moved=${m.moved} existed=${m.existed} skip=${m.skipped}`,
  );
  console.log(`[migrate] done db cover_path updated=${db}`);
  await pool.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
