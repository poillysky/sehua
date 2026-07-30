import { promises as fs } from "fs";
import path from "path";
import { randomUUID } from "crypto";

import {
  collectDescendantIds,
  findFolder,
  isSearchItem,
  listChildren,
  type ZoneFolder,
  type ZoneFoldersStore,
  type ZoneItemKind,
} from "@/lib/zoneFolderModel";

export type {
  ZoneFolder,
  ZoneFoldersStore,
  ZoneItemKind,
} from "@/lib/zoneFolderModel";

export {
  listChildren,
  findFolder,
  folderAncestors,
  zoneFolderHref,
  zoneFolderActiveFid,
  parseZoneActiveFid,
  isZoneCustomCategory,
  isSearchItem,
  isFolderItem,
} from "@/lib/zoneFolderModel";

const CONFIG_DIR = path.join(process.cwd(), "data");
const CONFIG_PATH = path.join(CONFIG_DIR, "zone-folders.json");

const EMPTY: ZoneFoldersStore = {
  version: 1,
  folders: [],
  updatedAt: "",
};

function nowIso() {
  return new Date().toISOString();
}

function asStr(v: unknown): string {
  return String(v ?? "").trim();
}

function normalizeKind(
  raw: unknown,
  searchKeyword: string,
): ZoneItemKind {
  if (raw === "search" || raw === "folder") return raw;
  // 旧数据：有关键词视为搜索项
  return searchKeyword ? "search" : "folder";
}

function normalizeFolder(raw: unknown): ZoneFolder | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const id = asStr(o.id);
  const name = asStr(o.name);
  if (!id || !name) return null;
  const parentRaw = o.parentId;
  const parentId =
    parentRaw === null || parentRaw === undefined || parentRaw === ""
      ? null
      : asStr(parentRaw) || null;
  const sortOrder = Number(o.sortOrder);
  const searchKeyword = asStr(o.searchKeyword);
  const kind = normalizeKind(o.kind, searchKeyword);
  return {
    id,
    parentId,
    name,
    kind,
    searchKeyword: kind === "search" ? searchKeyword : "",
    sortOrder: Number.isFinite(sortOrder) ? sortOrder : 0,
    createdAt: asStr(o.createdAt) || nowIso(),
    updatedAt: asStr(o.updatedAt) || nowIso(),
  };
}

function normalizeStore(raw: unknown): ZoneFoldersStore {
  if (!raw || typeof raw !== "object") return { ...EMPTY, folders: [] };
  const o = raw as Record<string, unknown>;
  const folders: ZoneFolder[] = [];
  const seen = new Set<string>();
  if (Array.isArray(o.folders)) {
    for (const item of o.folders) {
      const f = normalizeFolder(item);
      if (!f || seen.has(f.id)) continue;
      seen.add(f.id);
      folders.push(f);
    }
  }
  return {
    version: 1,
    folders,
    updatedAt: asStr(o.updatedAt),
  };
}

export async function readZoneFolders(): Promise<ZoneFoldersStore> {
  try {
    const raw = await fs.readFile(CONFIG_PATH, "utf8");
    return normalizeStore(JSON.parse(raw));
  } catch {
    return { ...EMPTY, folders: [] };
  }
}

async function writeZoneFolders(store: ZoneFoldersStore): Promise<ZoneFoldersStore> {
  const next: ZoneFoldersStore = {
    version: 1,
    folders: store.folders,
    updatedAt: nowIso(),
  };
  await fs.mkdir(CONFIG_DIR, { recursive: true });
  await fs.writeFile(CONFIG_PATH, JSON.stringify(next, null, 2), "utf8");
  return next;
}

export type CreateZoneFolderInput = {
  name: string;
  parentId?: string | null;
  kind?: ZoneItemKind;
  searchKeyword?: string;
};

export async function createZoneFolder(
  input: CreateZoneFolderInput,
): Promise<{ store: ZoneFoldersStore; folder: ZoneFolder }> {
  const name = asStr(input.name);
  if (!name) throw new Error("名称不能为空");
  if (name.length > 80) throw new Error("名称过长");

  const searchKeyword = asStr(input.searchKeyword);
  const kind: ZoneItemKind =
    input.kind === "search" || input.kind === "folder"
      ? input.kind
      : searchKeyword
        ? "search"
        : "folder";

  if (kind === "search" && !searchKeyword) {
    throw new Error("搜索文件夹需要填写关键词");
  }

  const store = await readZoneFolders();
  const parentId =
    input.parentId === undefined || input.parentId === null || input.parentId === ""
      ? null
      : asStr(input.parentId);

  if (parentId) {
    const parent = findFolder(store.folders, parentId);
    if (!parent) throw new Error("上级目录不存在");
    if (isSearchItem(parent)) {
      throw new Error("搜索项下不能再建子项");
    }
  }

  const siblings = listChildren(store.folders, parentId);
  const ts = nowIso();
  const folder: ZoneFolder = {
    id: randomUUID().replace(/-/g, "").slice(0, 16),
    parentId,
    name,
    kind,
    searchKeyword: kind === "search" ? searchKeyword : "",
    sortOrder: siblings.length ? Math.max(...siblings.map((s) => s.sortOrder)) + 1 : 0,
    createdAt: ts,
    updatedAt: ts,
  };

  const next = await writeZoneFolders({
    ...store,
    folders: [...store.folders, folder],
  });
  return { store: next, folder };
}

export type UpdateZoneFolderInput = {
  name?: string;
  searchKeyword?: string;
  parentId?: string | null;
  sortOrder?: number;
};

export async function updateZoneFolder(
  id: string,
  input: UpdateZoneFolderInput,
): Promise<{ store: ZoneFoldersStore; folder: ZoneFolder }> {
  const store = await readZoneFolders();
  const idx = store.folders.findIndex((f) => f.id === asStr(id));
  if (idx < 0) throw new Error("目录不存在");

  const prev = store.folders[idx];
  let parentId = prev.parentId;
  if (input.parentId !== undefined) {
    parentId =
      input.parentId === null || input.parentId === ""
        ? null
        : asStr(input.parentId);
    if (parentId === prev.id) throw new Error("不能移动到自身");
    if (parentId) {
      const parent = findFolder(store.folders, parentId);
      if (!parent) throw new Error("上级目录不存在");
      if (isSearchItem(parent)) throw new Error("不能移动到搜索项下");
      const descendants = collectDescendantIds(store.folders, prev.id);
      if (descendants.has(parentId)) throw new Error("不能移动到子目录下");
    }
  }

  let name = prev.name;
  if (input.name !== undefined) {
    name = asStr(input.name);
    if (!name) throw new Error("名称不能为空");
    if (name.length > 80) throw new Error("名称过长");
  }

  let searchKeyword = prev.searchKeyword;
  if (input.searchKeyword !== undefined) {
    searchKeyword = asStr(input.searchKeyword);
    if (prev.kind === "search" && !searchKeyword) {
      throw new Error("搜索文件夹需要填写关键词");
    }
  }

  let sortOrder = prev.sortOrder;
  if (input.sortOrder !== undefined) {
    const n = Number(input.sortOrder);
    if (!Number.isFinite(n)) throw new Error("排序无效");
    sortOrder = n;
  }

  const folder: ZoneFolder = {
    ...prev,
    parentId,
    name,
    searchKeyword: prev.kind === "search" ? searchKeyword : "",
    sortOrder,
    updatedAt: nowIso(),
  };

  // 换了上级：默认排到新目录末尾
  if (input.parentId !== undefined && parentId !== prev.parentId && input.sortOrder === undefined) {
    const siblings = listChildren(store.folders, parentId).filter((s) => s.id !== prev.id);
    folder.sortOrder = siblings.length
      ? Math.max(...siblings.map((s) => s.sortOrder)) + 1
      : 0;
  }

  const folders = store.folders.slice();
  folders[idx] = folder;
  const next = await writeZoneFolders({ ...store, folders });
  return { store: next, folder };
}

export async function reorderZoneSiblings(
  parentId: string | null,
  orderedIds: string[],
): Promise<ZoneFoldersStore> {
  const store = await readZoneFolders();
  const siblings = listChildren(store.folders, parentId);
  if (!orderedIds.length || orderedIds.length !== siblings.length) {
    throw new Error("排序列表无效");
  }
  const sibSet = new Set(siblings.map((s) => s.id));
  for (const id of orderedIds) {
    if (!sibSet.has(id)) throw new Error("排序列表无效");
  }
  const orderMap = new Map(orderedIds.map((id, i) => [id, i]));
  const ts = nowIso();
  const folders = store.folders.map((f) => {
    const ord = orderMap.get(f.id);
    if (ord === undefined) return f;
    return { ...f, sortOrder: ord, updatedAt: ts };
  });
  return writeZoneFolders({ ...store, folders });
}

export async function importZoneFolders(
  rawFolders: unknown[],
): Promise<ZoneFoldersStore> {
  if (!Array.isArray(rawFolders)) throw new Error("导入数据无效");
  const folders: ZoneFolder[] = [];
  const seen = new Set<string>();
  for (const item of rawFolders) {
    const f = normalizeFolder(item);
    if (!f || seen.has(f.id)) continue;
    seen.add(f.id);
    folders.push(f);
  }
  // 丢掉指向不存在父级的边
  const ids = new Set(folders.map((f) => f.id));
  const cleaned = folders.map((f) => ({
    ...f,
    parentId: f.parentId && ids.has(f.parentId) ? f.parentId : null,
    searchKeyword: f.kind === "search" ? f.searchKeyword : "",
  }));
  for (const f of cleaned) {
    if (f.kind === "search" && !f.searchKeyword) {
      throw new Error(`搜索项「${f.name}」缺少关键词`);
    }
  }
  return writeZoneFolders({ version: 1, folders: cleaned, updatedAt: "" });
}

export async function deleteZoneFolder(id: string): Promise<ZoneFoldersStore> {
  const store = await readZoneFolders();
  const target = findFolder(store.folders, id);
  if (!target) throw new Error("目录不存在");
  const drop = collectDescendantIds(store.folders, target.id);
  return writeZoneFolders({
    ...store,
    folders: store.folders.filter((f) => !drop.has(f.id)),
  });
}
