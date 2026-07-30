import path from "node:path";

import {
  CODE_KIND_LABELS,
  detectCodeKind,
  type CodeKind,
} from "./sources/registry.js";

/** 磁盘目录名（与监控「模式」一致） */
export function kindDirName(kind: CodeKind): string {
  return CODE_KIND_LABELS[kind] || "有码";
}

/** 厂牌子目录：ABF-053→ABF；FC2-PPV-xxx→FC2；259LUXU-001→259LUXU */
export function makerDirName(code: string): string {
  const c = String(code || "")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "");
  if (!c) return "OTHER";
  if (/^FC2/.test(c)) return "FC2";
  const m =
    c.match(/^(\d{2,4}[A-Z]{2,10})-\d+/) ||
    c.match(/^([A-Z]{2,10})-\d+/);
  if (m?.[1]) return m[1].replace(/[^A-Z0-9_-]/g, "_");
  return "OTHER";
}

export function safeCodeFilename(code: string, ext: string): string {
  const base = String(code || "")
    .replace(/[^A-Za-z0-9_-]+/g, "_")
    .toUpperCase();
  const e = ext.startsWith(".") ? ext : `.${ext}`;
  return `${base}${e}`;
}

/**
 * 分级相对路径：有码/ABF/ABF-053.jpg
 * 使用正斜杠，便于写入 cover_path / URL。
 */
export function coverRelPath(code: string, kind?: CodeKind): string {
  const k = kind || detectCodeKind(code);
  return [
    kindDirName(k),
    makerDirName(code),
    safeCodeFilename(code, ".jpg"),
  ].join("/");
}

export function metaRelPath(code: string, kind?: CodeKind): string {
  const k = kind || detectCodeKind(code);
  return [
    kindDirName(k),
    makerDirName(code),
    safeCodeFilename(code, ".json"),
  ].join("/");
}

/** 候选相对路径：分级优先，再兼容旧扁平 CODE.jpg */
export function coverRelCandidates(code: string, kind?: CodeKind): string[] {
  const nested = coverRelPath(code, kind);
  const flat = safeCodeFilename(code, ".jpg");
  const out = [nested];
  // 若强制了 kind，也试自动识别的分级路径
  if (kind) {
    const auto = coverRelPath(code);
    if (auto !== nested) out.push(auto);
  }
  out.push(flat);
  return out;
}

export function metaRelCandidates(code: string, kind?: CodeKind): string[] {
  const nested = metaRelPath(code, kind);
  const flat = safeCodeFilename(code, ".json");
  const out = [nested];
  if (kind) {
    const auto = metaRelPath(code);
    if (auto !== nested) out.push(auto);
  }
  out.push(flat);
  return out;
}

export function toPosixRel(...parts: string[]): string {
  return path.posix.join(
    ...parts.map((p) => p.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "")),
  );
}
