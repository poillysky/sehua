import path from "node:path";

/** 本地默认相对路径；容器通过 ENV COVERS_DIR=/data/covers 覆盖 */
export const DEFAULT_COVERS_DIR = "data/covers";
export const DEFAULT_META_DIR = "data/meta";

let coversConfigured =
  (process.env.COVERS_DIR || "").trim() || DEFAULT_COVERS_DIR;
let metaConfigured = (process.env.META_DIR || "").trim() || DEFAULT_META_DIR;

/**
 * 规范化为容器友好路径：统一 `/`，去掉末尾斜杠。
 * 相对路径（如 data/covers）与绝对容器路径（/data/covers）均可。
 */
export function normalizeDataPath(raw: string, fallback: string): string {
  let p = String(raw || "")
    .trim()
    .replace(/\\/g, "/");
  if (!p) p = fallback;
  // 拒绝宿主机盘符路径，强制容器/相对路径
  if (/^[A-Za-z]:\//.test(p)) {
    throw new Error(
      "请使用容器路径（如 /data/covers）或相对路径（如 data/covers），不要填盘符绝对路径",
    );
  }
  if (p.startsWith("/")) {
    return p.replace(/\/+$/, "") || fallback;
  }
  // 相对路径：禁止 .. 逃逸
  const parts = p.split("/").filter((x) => x && x !== ".");
  if (parts.some((x) => x === "..")) {
    throw new Error("目录不允许包含 ..");
  }
  return parts.join("/") || fallback;
}

/** 运行时解析为当前进程可写的绝对路径（cwd 相对或容器绝对） */
export function resolveDataPath(configured: string): string {
  const p = normalizeDataPath(configured, configured);
  if (p.startsWith("/")) {
    // Unix 绝对路径（容器内）；Windows 上也会落到当前盘根，本地请改用相对路径
    return path.normalize(p);
  }
  return path.resolve(process.cwd(), p);
}

export function getCoversDirConfigured(): string {
  return coversConfigured;
}

export function getMetaDirConfigured(): string {
  return metaConfigured;
}

export function getCoversDir(): string {
  return resolveDataPath(coversConfigured);
}

export function getMetaDir(): string {
  return resolveDataPath(metaConfigured);
}

export function setDataDirs(input: {
  coversDir?: string;
  metaDir?: string;
}): { coversDir: string; metaDir: string } {
  if (input.coversDir !== undefined) {
    coversConfigured = normalizeDataPath(
      input.coversDir,
      DEFAULT_COVERS_DIR,
    );
  }
  if (input.metaDir !== undefined) {
    metaConfigured = normalizeDataPath(input.metaDir, DEFAULT_META_DIR);
  }
  return {
    coversDir: coversConfigured,
    metaDir: metaConfigured,
  };
}

/** 启动或读配置后应用目录 */
export function applyDataDirsFromConfig(cfg: {
  coversDir?: string | null;
  metaDir?: string | null;
}): void {
  // 配置优先于环境变量默认值；空则保留当前（含 env）
  if (cfg.coversDir != null && String(cfg.coversDir).trim()) {
    coversConfigured = normalizeDataPath(
      String(cfg.coversDir),
      coversConfigured,
    );
  }
  if (cfg.metaDir != null && String(cfg.metaDir).trim()) {
    metaConfigured = normalizeDataPath(String(cfg.metaDir), metaConfigured);
  }
}
